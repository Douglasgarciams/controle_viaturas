# Seu topo do arquivo, garantindo que 'tempfile' e 'os' estejam importados
from dotenv import load_dotenv
load_dotenv() # Carrega as variáveis de ambiente do .env
import os
import MySQLdb
import pytz
import unicodedata # Importante para limpeza de texto
from flask import Flask, render_template, request, redirect, url_for, flash, g
from datetime import datetime, timedelta, time
import pandas as pd
from flask import send_file
from io import BytesIO
import tempfile 

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'sua-chave-secreta-para-desenvolvimento-local')

# --- Funções para Gerenciar a Conexão com o Banco de Dados ---
def get_db():
    if 'db' not in g:
        db_host = os.environ.get('DB_HOST')
        db_port = int(os.environ.get('DB_PORT', 4000))
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME')
        ca_cert_content = os.environ.get('CA_CERT_CONTENT')

        ca_path = None
        if ca_cert_content:
            temp_ca_file = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8')
            temp_ca_file.write(ca_cert_content)
            temp_ca_file.close()
            ca_path = temp_ca_file.name
        else:
            local_ca_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ca.pem')
            if os.path.exists(local_ca_path):
                ca_path = local_ca_path

        g.db = MySQLdb.connect(
            host=db_host, port=db_port, user=db_user, passwd=db_password, db=db_name,
            ssl_mode='VERIFY_IDENTITY', ssl={'ca': ca_path} if ca_path else {}
        )
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# --- Funções Auxiliares ---
def format_minutes_to_hh_mm(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"

def ensure_hh_mm_format_for_display(time_value):
    if isinstance(time_value, time): return time_value.strftime("%H:%M")
    if isinstance(time_value, str) and len(time_value) == 5 and ':' in time_value: return time_value
    return ''

# 🔧 Status disponíveis
STATUS_OPTIONS = ['ADM', 'CFP', 'FORÇA TATICA', 'RP', 'TRANSITO', 'ADJ CFP', 'INTERIOR', 'MOTO', 'ROTAC', 'CANIL', 'BOPE', 'ESCOLAR/PROMUSE', 'POL.COMUNITARIO', 'JUIZADO', 'TRANSITO/BLITZ']

# 🚨 Lista de Delegacias disponíveis para seleção
LISTA_DELEGACIAS = [
    "1º DP", "2º DP", "3º DP", "4º DP", "5º DP", "6º DP", "7º DP", 
    "DEPAC – CENTRO", "DEPAC – CEPOL", "DECCO", "DECCOR", "LAB LD/DRACCO", 
    "DEAM", "DEAIJ", "DECAT", "DECON", "DEDFAZ", "DEFURV", "DHPP", "DENAR", 
    "DEOPS", "DEPCA", "DERF", "DEVIR", "GARRAS", "POLINTER", "DELETRAN", "POLICIA FEDERAL", "CORREGEDORIA PMMS" ,
    "DELEAGRO"
]

# --- ROTAS DO SISTEMA ---

@app.route('/', methods=['GET', 'POST'])
def index():
    conn = None
    cursor = None
    supervisores_data = {'supervisor_operacoes': '', 'coordenador': '', 'supervisor_despacho': '', 'supervisor_atendimento': '', 'last_updated': None}
    unidades = []
    viaturas = []
    contatos = []

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST' and 'supervisorOperacoes' in request.form:
            supervisor_operacoes = request.form.get('supervisorOperacoes', '')
            coordenador = request.form.get('coordenador', '')
            supervisor_despacho = request.form.get('supervisorDespacho', '')
            supervisor_atendimento = request.form.get('supervisorAtendimento', '')
            fuso_horario_ms = pytz.timezone('America/Campo_Grande')
            current_time = datetime.now(fuso_horario_ms)

            sql_update = """UPDATE supervisores SET supervisor_operacoes=%s, coordenador=%s, supervisor_despacho=%s, supervisor_atendimento=%s, last_updated=%s WHERE id=1"""
            cursor.execute(sql_update, (supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento, current_time))
            conn.commit()
            flash('Supervisores salvos com sucesso!', 'success')
            return redirect(url_for('index'))

        elif request.method == 'POST' and request.form.get('tipo') == 'contato':
             unidade_id = request.form.get('unidade')
             nome_cfp = request.form.get('nome')
             telefone = request.form.get('telefone')
             cursor.execute("SELECT * FROM contatos WHERE unidade_id=%s", (unidade_id,))
             if cursor.fetchone():
                 cursor.execute("UPDATE contatos SET cfp=%s, telefone=%s WHERE unidade_id=%s", (nome_cfp, telefone, unidade_id))
             else:
                 cursor.execute("INSERT INTO contatos (unidade_id, cfp, telefone) VALUES (%s, %s, %s)", (unidade_id, nome_cfp, telefone))
             conn.commit()
             flash('Contato salvo com sucesso!', 'success')
             return redirect(url_for('index'))

        cursor.execute("SELECT * FROM supervisores WHERE id = 1")
        row = cursor.fetchone()
        if row: supervisores_data = row

        cursor.execute("SELECT * FROM unidades")
        unidades = cursor.fetchall()

        cursor.execute("SELECT v.id, v.prefixo, v.unidade_id, v.status, u.nome_unidade AS unidade_nome FROM viaturas v JOIN unidades u ON v.unidade_id = u.id ORDER BY u.nome_unidade, v.prefixo")
        viaturas = cursor.fetchall()

        cursor.execute("SELECT c.*, u.nome_unidade AS unidade_nome FROM contatos c JOIN unidades u ON c.unidade_id = u.id")
        contatos = cursor.fetchall()

    except MySQLdb.Error as err:
        flash(f"Database error: {err}", 'danger')
    finally:
        if cursor: cursor.close()

    return render_template('index.html', unidades=unidades, status_options=STATUS_OPTIONS, viaturas=viaturas, contatos=contatos, supervisores=supervisores_data)

@app.route('/cadastro_viaturas', methods=['GET', 'POST'])
def cadastro_viaturas():
    conn = None
    cursor = None
    unidades = []
    viaturas = []
    contatos = []
    contagem_viaturas_por_unidade = {}
    unidade_filtro = request.args.get('unidade_id')

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            unidade_id_form = request.form['unidade_id']
            prefixo = request.form['prefixo'].strip()
            status = request.form['status']
            hora_entrada = request.form.get('hora_entrada')
            hora_saida = request.form.get('hora_saida')

            cursor.execute("SELECT id FROM viaturas WHERE prefixo = %s", (prefixo,))
            if cursor.fetchone():
                flash(f'O prefixo "{prefixo}" já está cadastrado.', 'danger')
                return redirect(url_for('cadastro_viaturas', unidade_id=unidade_filtro))
            else:
                cursor.execute("INSERT INTO viaturas (unidade_id, prefixo, status, hora_entrada, hora_saida) VALUES (%s, %s, %s, %s, %s)", (unidade_id_form, prefixo, status, hora_entrada, hora_saida))
                conn.commit()
                flash('Viatura cadastrada com sucesso!', 'success')
                return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id_form))

        cursor.execute("SELECT id, nome_unidade AS nome FROM unidades")
        unidades = cursor.fetchall()

        query_viaturas = "SELECT v.id, u.nome_unidade AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida FROM viaturas v JOIN unidades u ON v.unidade_id = u.id"
        if unidade_filtro:
            query_viaturas += " WHERE v.unidade_id = %s ORDER BY v.prefixo ASC"
            cursor.execute(query_viaturas, (unidade_filtro,))
        else:
            query_viaturas += " ORDER BY u.nome_unidade ASC, v.prefixo ASC"
            cursor.execute(query_viaturas)
        viaturas = cursor.fetchall()

        cursor.execute("SELECT unidade_id, COUNT(*) as quantidade FROM viaturas GROUP BY unidade_id")
        contagem_viaturas_por_unidade = {row['unidade_id']: row['quantidade'] for row in cursor.fetchall()}

        cursor.execute("SELECT c.id, u.nome_unidade AS unidade_nome, c.cfp, c.telefone FROM contatos c JOIN unidades u ON c.unidade_id = u.id")
        contatos = cursor.fetchall()

    except MySQLdb.Error as err:
        flash(f"Database error: {err}", 'danger')
    finally:
        if cursor: cursor.close()

    return render_template('cadastro_viaturas.html', unidades=unidades, viaturas=viaturas, contatos=contatos, unidade_filtro=unidade_filtro, contagem_viaturas_por_unidade=contagem_viaturas_por_unidade)

# --- ROTAS CRUD VIATURAS/CONTATOS ---
@app.route('/editar_contato/<int:contato_id>', methods=['GET', 'POST'])
def editar_contato(contato_id):
    conn = None
    cursor = None
    contato = None
    unidades = [] # Inicializa a lista

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        
        # 1. Processa o Formulário (POST)
        if request.method == 'POST':
            unidade_id = request.form['unidade_id']
            cfp = request.form['cfp']
            telefone = request.form['telefone']
            cursor.execute("UPDATE contatos SET unidade_id = %s, cfp = %s, telefone = %s WHERE id = %s", (unidade_id, cfp, telefone, contato_id))
            conn.commit()
            flash('Contato atualizado com sucesso!', 'success')
            return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

        # 2. Busca os dados do Contato (GET)
        cursor.execute("SELECT * FROM contatos WHERE id = %s", (contato_id,))
        contato = cursor.fetchone()
        
        # 3. Busca a lista de Unidades para o dropdown (FALTAVA ISSO)
        cursor.execute("SELECT * FROM unidades ORDER BY nome_unidade ASC")
        unidades = cursor.fetchall()

    except MySQLdb.Error as err:
        flash(f"Database error: {err}", 'danger')
        return redirect(url_for('cadastro_viaturas'))
    finally:
        if cursor: cursor.close()

    if contato is None:
        flash('Contato não encontrado.', 'danger')
        return redirect(url_for('cadastro_viaturas'))

    # Passa 'contato' E 'unidades' para o template
    return render_template('editar_contato.html', contato=contato, unidades=unidades)

@app.route('/adicionar_contato', methods=['POST'])
def adicionar_contato():
    conn = None
    cursor = None
    unidade_id = request.form.get('unidade_id', '')
    try:
        unidade_id = request.form['unidade_id']
        cfp = request.form['cfp']
        telefone = request.form['telefone']
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO contatos (unidade_id, cfp, telefone) VALUES (%s, %s, %s)", (unidade_id, cfp, telefone))
        conn.commit()
        flash('Contato cadastrado com sucesso!', 'success')
    except MySQLdb.Error as err:
        flash(f"Database error: {err}", 'danger')
    finally:
        if cursor: cursor.close()
    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/excluir_contato/<int:contato_id>', methods=['POST'])
def excluir_contato(contato_id):
    conn = None
    cursor = None
    unidade_id = ''
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT unidade_id FROM contatos WHERE id = %s", (contato_id,))
        contato = cursor.fetchone()
        unidade_id = contato['unidade_id'] if contato else ''
        cursor.execute("DELETE FROM contatos WHERE id = %s", (contato_id,))
        conn.commit()
        flash('Contato excluído com sucesso!', 'success')
    except MySQLdb.Error as err:
        flash(f'Database error: {err}', 'danger')
    finally:
        if cursor: cursor.close()
    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/excluir_viatura/<int:viatura_id>', methods=['POST'])
def excluir_viatura(viatura_id):
    conn = None
    cursor = None
    unidade_id = ''
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT unidade_id FROM viaturas WHERE id = %s", (viatura_id,))
        viatura = cursor.fetchone()
        if not viatura:
            flash('Viatura não encontrada.', 'danger')
            return redirect(url_for('cadastro_viaturas'))
        unidade_id = viatura['unidade_id']
        cursor.execute("DELETE FROM viaturas WHERE id = %s", (viatura_id,))
        conn.commit()
        flash('Viatura excluída com sucesso!', 'success')
    except MySQLdb.Error as err:
        flash(f'Database error: {err}', 'danger')
    finally:
        if cursor: cursor.close()
    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/editar_viatura/<int:viatura_id>', methods=['GET', 'POST'])
def editar_viatura(viatura_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            unidade_id = request.form['unidade_id']
            prefixo = request.form['prefixo'].strip()
            status = request.form['status']
            hora_entrada = request.form.get('hora_entrada')
            hora_saida = request.form.get('hora_saida')

            cursor.execute("SELECT id FROM viaturas WHERE prefixo = %s AND id != %s", (prefixo, viatura_id))
            if cursor.fetchone():
                flash(f'O prefixo "{prefixo}" já está em uso.', 'danger')
                return redirect(url_for('editar_viatura', viatura_id=viatura_id))

            cursor.execute("""
                UPDATE viaturas
                SET unidade_id = %s, prefixo = %s, status = %s, hora_entrada = %s, hora_saida = %s
                WHERE id = %s
            """, (unidade_id, prefixo, status, hora_entrada, hora_saida, viatura_id))
            conn.commit()
            flash('Viatura atualizada!', 'success')
            return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

        cursor.execute("SELECT * FROM viaturas WHERE id = %s", (viatura_id,))
        viatura = cursor.fetchone()
        if not viatura:
            return redirect(url_for('cadastro_viaturas'))

        cursor.execute("SELECT id, nome_unidade FROM unidades ORDER BY nome_unidade")
        unidades = cursor.fetchall()
        return render_template('editar_viatura.html', viatura=viatura, unidades=unidades)

    except MySQLdb.Error as err:
        flash(f"Database error: {err}", 'danger')
        return redirect(url_for('cadastro_viaturas'))
    finally:
        if cursor: cursor.close()


# ==============================================================================
# ROTAS DE OCORRÊNCIAS (COM LISTA DE FATOS DO BANCO)
# ==============================================================================

@app.route('/ocorrencias', methods=['GET', 'POST'])
def gerenciar_ocorrencias():
    conn = None
    cursor = None
    ocorrencias = []
    lista_fatos_db = []

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        # 1. Busca lista de fatos para o dropdown
        cursor.execute("SELECT nome FROM tipos_fatos ORDER BY nome ASC")
        lista_fatos_db = cursor.fetchall()

        if request.method == 'POST':
            delegacia = request.form.get('delegacia', '').strip()
            viatura_prefixo = request.form.get('viatura_prefixo', '').strip()
            fato = request.form.get('fato', '').strip()
            status = request.form.get('status', '').strip()
            protocolo = request.form.get('protocolo', '').strip()
            ro_cadg = request.form.get('ro_cadg', '').strip()
            chegada = request.form.get('chegada', '').strip()
            entrega_ro = request.form.get('entrega_ro', '').strip()
            saida = request.form.get('saida', '').strip()

            fuso_horario_ms = pytz.timezone('America/Campo_Grande')
            data_do_registro = datetime.now(fuso_horario_ms)
            
            tempo_total_dp = None
            tempo_entrega_dp = None
            if chegada and entrega_ro and saida:
                try:
                    fmt = "%H:%M"
                    chegada_dt = datetime.strptime(chegada, fmt)
                    entrega_dt = datetime.strptime(entrega_ro, fmt)
                    saida_dt = datetime.strptime(saida, fmt)
                    if saida_dt < chegada_dt: saida_dt += timedelta(days=1)
                    if entrega_dt < chegada_dt: entrega_dt += timedelta(days=1)
                    tempo_total_dp = format_minutes_to_hh_mm(int((saida_dt - chegada_dt).total_seconds() // 60))
                    tempo_entrega_dp = format_minutes_to_hh_mm(int((entrega_dt - chegada_dt).total_seconds() // 60))
                except ValueError:
                    flash('Formato de horário inválido.', 'danger')
                    return redirect(url_for('gerenciar_ocorrencias'))

            cursor.execute("""
                INSERT INTO ocorrencias_cepol
                (delegacia, viatura_prefixo, fato, status, protocolo, ro_cadg, chegada_delegacia, entrega_ro, saida_delegacia, tempo_total_dp, tempo_entrega_dp, data_registro)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (delegacia or None, viatura_prefixo or None, fato or None, status or None, protocolo or None, ro_cadg or None, chegada or None, entrega_ro or None, saida or None, tempo_total_dp, tempo_entrega_dp, data_do_registro))

            conn.commit()
            flash('Ocorrência registrada com sucesso!', 'success')
            return redirect(url_for('gerenciar_ocorrencias'))

        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY data_registro DESC")
        ocorrencias = cursor.fetchall()

    except MySQLdb.Error as err:
        flash(f"Erro no banco: {err}", 'danger')
    except Exception as e:
        flash(f"Erro inesperado: {e}", 'danger')
    finally:
        if cursor: cursor.close()

    return render_template('ocorrencias_cepol.html', ocorrencias=ocorrencias, lista_fatos_db=lista_fatos_db, lista_delegacias=LISTA_DELEGACIAS)

# ✏️ Rota para editar ocorrência (com campo de viatura e delegacia)
@app.route('/editar_ocorrencia/<int:id>', methods=['GET', 'POST'])
def editar_ocorrencia(id):
    conn = None
    cursor = None
    lista_fatos_db = []
    # 🚨 NOVO: Variável para armazenar a lista de delegacias 🚨
    lista_delegacias = [] 
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        # 1. Busca a lista de fatos (OK)
        cursor.execute("SELECT nome FROM tipos_fatos ORDER BY nome ASC")
        lista_fatos_db = cursor.fetchall()

        # 2. Busca a lista de delegacias (A CORREÇÃO)
        # Se você tiver uma tabela de delegacias:
        # cursor.execute("SELECT nome FROM delegacias ORDER BY nome ASC")
        # lista_delegacias_db = [item['nome'] for item in cursor.fetchall()]

        # Se a lista de delegacias for fixa (como no seu código HTML original):
        lista_delegacias = [
            "1ª DP", "2ª DP", "3ª DP", "4ª DP", "5ª DP", "6ª DP", "7ª DP",
            "DEPAC CENTRO", "DEPAC CEPOL", "DEAM", "DCA", "DEFURV", "DERF", 
            "DENAR", "DEH", "DEOPS", "GARRAS", "POLINTER"
        ]
        
        # Lógica POST (Atualizar)
        if request.method == 'POST':
            # ... (Seu código de POST continua aqui, usando a variável 'delegacia') ...
            delegacia = request.form.get('delegacia', '').strip()
            fato = request.form.get('fato', '').strip()
            # ... (restante do código de POST) ...
            status = request.form.get('status', '').strip()
            protocolo = request.form.get('protocolo', '').strip()
            viatura_prefixo = request.form.get('viatura_prefixo', '').strip()
            ro_cadg = request.form.get('ro_cadg', '').strip()
            chegada = request.form.get('chegada', '').strip()
            entrega_ro = request.form.get('entrega_ro', '').strip()
            saida = request.form.get('saida', '').strip()

            # Cálculo de tempo (igual ao cadastro)
            tempo_total_dp = None
            tempo_entrega_dp = None
            if chegada and entrega_ro and saida:
                try:
                    fmt = "%H:%M"
                    chegada_dt = datetime.strptime(chegada, fmt)
                    entrega_dt = datetime.strptime(entrega_ro, fmt)
                    saida_dt = datetime.strptime(saida, fmt)
                    if saida_dt < chegada_dt: saida_dt += timedelta(days=1)
                    if entrega_dt < chegada_dt: entrega_dt += timedelta(days=1)
                    tempo_total_dp = format_minutes_to_hh_mm(int((saida_dt - chegada_dt).total_seconds() // 60))
                    tempo_entrega_dp = format_minutes_to_hh_mm(int((entrega_dt - chegada_dt).total_seconds() // 60))
                except ValueError:
                    flash('Formato de horário inválido. Utilize HH:MM.', 'danger')
                    return redirect(url_for('editar_ocorrencia', id=id))

            # Comando UPDATE
            cursor.execute("""
                UPDATE ocorrencias_cepol
                SET delegacia=%s, fato=%s, status=%s, protocolo=%s, ro_cadg=%s, viatura_prefixo=%s, 
                    chegada_delegacia=%s, entrega_ro=%s, saida_delegacia=%s, 
                    tempo_total_dp=%s, tempo_entrega_dp=%s
                WHERE id = %s
            """, (delegacia or None, fato, status, protocolo, ro_cadg, viatura_prefixo or None, 
                  chegada or None, entrega_ro or None, saida or None, 
                  tempo_total_dp, tempo_entrega_dp, id))
            
            conn.commit()
            flash('Ocorrência atualizada com sucesso!', 'success')
            return redirect(url_for('gerenciar_ocorrencias'))

        # --- Lógica de GET (Exibir Formulário) ---
        cursor.execute("SELECT * FROM ocorrencias_cepol WHERE id = %s", (id,))
        ocorrencia = cursor.fetchone()

        if not ocorrencia:
            flash('Ocorrência não encontrada.', 'danger')
            return redirect(url_for('gerenciar_ocorrencias'))

        # Formatação de tempo para exibição no formulário
        ocorrencia['chegada_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('chegada_delegacia'))
        ocorrencia['entrega_ro'] = ensure_hh_mm_format_for_display(ocorrencia.get('entrega_ro'))
        ocorrencia['saida_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('saida_delegacia'))

    except MySQLdb.Error as err:
        flash(f"Erro no banco de dados ao carregar/atualizar: {err}", 'danger')
        return redirect(url_for('gerenciar_ocorrencias'))
    except Exception as e:
        # Catch other potential errors like datetime formatting
        flash(f"Ocorreu um erro: {e}", 'danger')
        return redirect(url_for('gerenciar_ocorrencias'))
    finally:
        if cursor:
            cursor.close()

    # 🔑 A MUDANÇA PRINCIPAL: Passar lista_delegacias para o template
    return render_template('editar_ocorrencia.html', 
                           ocorrencia=ocorrencia, 
                           lista_fatos_db=lista_fatos_db,
                           lista_delegacias=lista_delegacias)

@app.route('/arquivar_ocorrencia/<int:id>', methods=['POST'])
def arquivar_ocorrencia(id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # Em vez de DELETAR, vamos ATUALIZAR o status para 'arquivado' e registrar a data
        query = "UPDATE ocorrencias_cepol SET status = 'arquivado', arquivado_em = %s WHERE id = %s"
        data_arquivamento = datetime.now()
        cursor.execute(query, (data_arquivamento, id))
        conn.commit()
        flash('Ocorrência arquivada com sucesso!', 'success')
    except MySQLdb.Error as err:
        flash(f'Erro ao arquivar: {err}', 'danger')
    finally:
        if cursor: cursor.close()
    return redirect(url_for('gerenciar_ocorrencias'))

@app.route('/excluir_ocorrencia/<int:id>', methods=['POST'])
def excluir_ocorrencia(id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ocorrencias_cepol WHERE id = %s", (id,))
        conn.commit()
        flash('Ocorrência excluída com sucesso!', 'success')
    except MySQLdb.Error as err:
        flash(f'Erro ao excluir: {err}', 'danger')
    finally:
        if cursor: cursor.close()
    return redirect(url_for('gerenciar_ocorrencias'))

@app.route('/limpar_todas_ocorrencias', methods=['POST'])
def limpar_todas_ocorrencias():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        conn.begin()
        cursor.execute("INSERT INTO historico_ocorrencias SELECT * FROM ocorrencias_cepol")
        cursor.execute("DELETE FROM ocorrencias_cepol")
        conn.commit()
        flash('Ocorrências arquivadas com sucesso!', 'success')
    except MySQLdb.Error as err:
        if conn: conn.rollback()
        flash(f'Erro ao arquivar: {err}', 'danger')
    finally:
        if cursor: cursor.close()
    return redirect(url_for('gerenciar_ocorrencias'))

@app.route('/backup_ocorrencias_excel')
def backup_ocorrencias_excel():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY id ASC")
        ocorrencias = cursor.fetchall()

        if not ocorrencias:
            flash('Não há ocorrências para backup.', 'info')
            return redirect(url_for('gerenciar_ocorrencias'))

        df = pd.DataFrame(ocorrencias)
        output = BytesIO()
        nome_arquivo = f"backup_ocorrencias_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"
        df.to_excel(output, index=False, sheet_name='Backup_Ocorrencias')
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=nome_arquivo)
    except Exception as e:
        flash(f"Erro no backup: {e}", 'danger')
        return redirect(url_for('gerenciar_ocorrencias'))
    finally:
        if cursor: cursor.close()

# --- ROTAS HISTÓRICO ---
@app.route('/historico')
def historico():
    conn = None
    cursor = None
    historico_ocorrencias = []
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM historico_ocorrencias ORDER BY id DESC")
        historico_ocorrencias = cursor.fetchall()
    except MySQLdb.Error as err:
        flash(f"Erro ao carregar o histórico: {err}", 'danger')
    finally:
        if cursor: cursor.close()
    return render_template('historico.html', ocorrencias=historico_ocorrencias)

@app.route('/zerar_historico_confirmado', methods=['POST'])
def zerar_historico_confirmado():
    senha_digitada = request.form.get('password')
    SENHA_MESTRA = "copomadmin2025" 
    if senha_digitada == SENHA_MESTRA:
        conn = None
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("TRUNCATE TABLE historico_ocorrencias")
            conn.commit()
            flash('Histórico zerado!', 'success')
        except MySQLdb.Error as err:
            flash(f"Erro ao limpar histórico: {err}", "danger")
        finally:
            if 'cursor' in locals() and cursor: cursor.close()
    else:
        flash('Senha incorreta!', 'danger')
    return redirect(url_for('historico'))

@app.route('/exportar_historico_excel')
def exportar_historico_excel():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM historico_ocorrencias ORDER BY id ASC")
        ocorrencias = cursor.fetchall()

        if not ocorrencias:
            flash('Histórico vazio.', 'info')
            return redirect(url_for('historico'))

        df = pd.DataFrame(ocorrencias)
        colunas_de_horario = ['chegada_delegacia', 'entrega_ro', 'saida_delegacia']
        def formatar_timedelta_para_hora(td):
            if pd.isnull(td): return ''
            segundos_totais = int(td.total_seconds())
            horas, resto = divmod(segundos_totais, 3600)
            minutos, segundos = divmod(resto, 60)
            return f"'{horas:02}:{minutos:02}:{segundos:02}"

        for coluna in colunas_de_horario:
            if coluna in df.columns:
                df[coluna] = df[coluna].apply(formatar_timedelta_para_hora)

        output = BytesIO()
        nome_arquivo = f"historico_completo_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='Historico_Completo')
        writer.close()
        output.seek(0)

        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=nome_arquivo)
    except Exception as e:
        flash(f"Erro ao gerar Excel: {e}", 'danger')
        return redirect(url_for('historico'))
    finally:
        if cursor: cursor.close()

# --- ROTA RELATÓRIOS ---
@app.route('/relatorios')
def relatorios():
    conn = None
    cursor = None
    supervisores_string = "Nenhum supervisor."
    cfps_data = []
    viaturas_data = []
    viaturas_por_unidade = []
    viaturas_por_status = []
    totais_viaturas = {}

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        
        cursor.execute("SELECT supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento FROM supervisores WHERE id = 1")
        supervisores_db_row = cursor.fetchone()
        if supervisores_db_row:
            supervisores_parts = [f"<strong>{k.replace('_', ' ').title()}:</strong> {v}" for k, v in supervisores_db_row.items() if v]
            if supervisores_parts: supervisores_string = " - ".join(supervisores_parts)

        cursor.execute("SELECT c.id, u.nome_unidade AS unidade_nome, c.cfp, c.telefone FROM contatos c JOIN unidades u ON c.unidade_id = u.id ORDER BY u.nome_unidade, c.cfp")
        cfps_data = cursor.fetchall()

        cursor.execute("SELECT v.*, u.nome_unidade AS unidade_nome FROM viaturas v JOIN unidades u ON v.unidade_id = u.id ORDER BY u.nome_unidade, v.prefixo")
        viaturas_data = cursor.fetchall()

        cursor.execute("SELECT u.nome_unidade AS unidade_nome, COUNT(v.id) AS quantidade FROM viaturas v JOIN unidades u ON v.unidade_id = u.id GROUP BY u.nome_unidade ORDER BY u.nome_unidade")
        viaturas_por_unidade = cursor.fetchall()

        cursor.execute("SELECT status, COUNT(id) AS quantidade FROM viaturas GROUP BY status ORDER BY status")
        viaturas_por_status = cursor.fetchall()

        cursor.execute("SELECT status FROM viaturas")
        lista_status_raw = cursor.fetchall()

        if lista_status_raw:
            df = pd.DataFrame(lista_status_raw)
            df['status'] = df['status'].fillna('').str.strip()
            total_interior = (df['status'] == 'INTERIOR').sum()
            total_motos = (df['status'] == 'MOTO').sum()
            status_capital = ['ADM', 'CFP', 'FORÇATÁTICA', 'RP', 'TRÂNSITO', 'ADJ CFP', 'ROTAC', 'CANIL', 'BOPE', 'ESCOLAR/PROMUSE', 'POL.COMUNITÁRIO', 'TRANSITO/BLITZ']
            total_capital = df['status'].isin(status_capital).sum()
            soma_atendimento_copom = df['status'].isin(['FORÇATÁTICA', 'RP', 'TRÂNSITO']).sum()
            total_viaturas_geral = len(df)

            totais_viaturas = {
                'total_viaturas_geral': int(total_viaturas_geral),
                'total_capital': int(total_capital),
                'total_interior': int(total_interior),
                'total_motos': int(total_motos),
                'soma_atendimento_copom': int(soma_atendimento_copom),
                'total_capital_interior_motos': int(total_viaturas_geral)
            }
    except MySQLdb.Error as err:
        flash(f"Erro no banco: {err}", 'danger')
    finally:
        if cursor: cursor.close()

    return render_template('relatorios.html', supervisores_string=supervisores_string, cfps=cfps_data, viaturas=viaturas_data, viaturas_por_unidade=viaturas_por_unidade, viaturas_por_status=viaturas_por_status, totais_viaturas=totais_viaturas)

# --- DASHBOARD ---
# --- DASHBOARD ---
@app.route('/dashboard')
def dashboard():
    conn = None
    cursor = None
    kpis = {'total_ocorrencias': 0, 'delegacia_top': 'N/D', 'media_tempo_dp': '00:00'}
    dados_fatos_paginados = []
    dados_mensais = []
    status_chart_data = {}

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM historico_ocorrencias")
        historico_completo = cursor.fetchall()

        if historico_completo:
            df = pd.DataFrame(historico_completo)
            
            # --- FUNÇÕES DE LIMPEZA ---
            def limpar_texto(texto):
                if not isinstance(texto, str): return 'OUTROS'
                texto_sem_acento = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
                return texto_sem_acento.replace('.', '').replace('-', ' ').strip().upper()

            df['data_registro'] = pd.to_datetime(df['data_registro'])
            df['fato_limpo'] = df['fato'].apply(limpar_texto)
            df['delegacia'] = df['delegacia'].fillna('N/D').str.strip().str.upper()
            df['status'] = df['status'].fillna('N/A').str.strip().str.upper()
            
            delegacia_mapa = {'DEPAC CEPOL': 'CEPOL'}
            df['delegacia'] = df['delegacia'].replace(delegacia_mapa)
            
            palavras_chave_fatos = ['VIOLENCIA DOMESTICA', 'DIRECAO PERIGOSA', 'LESAO CORPORAL', 'HOMICIDIO', 'ROUBO', 'FURTO', 'TRAFICO', 'EVASAO', 'AMEACA', 'TCO', 'APF', 'ENTREGA', 'MANDADO DE PRISAO', 'VIAS DE FATO', 'PERTURBACAO', 'DANO', 'DESACATO']
            def agrupar_fato(fato_limpo):
                for chave in palavras_chave_fatos:
                    if chave in fato_limpo: return chave
                return fato_limpo
            df['fato_agrupado'] = df['fato_limpo'].apply(agrupar_fato)

            # --- KPIS ---
            kpis['total_ocorrencias'] = len(df)
            if not df['delegacia'].dropna().empty:
                kpis['delegacia_top'] = df['delegacia'].mode().get(0, 'N/D')
            
            # --- LÓGICA NOVA: AGRUPAR FATOS <= 5 ---
            contagem_fatos = df['fato_agrupado'].value_counts().reset_index()
            contagem_fatos.columns = ['fato', 'quantidade']
            
            # Separa o que é grande do que é pequeno
            fatos_principais = contagem_fatos[contagem_fatos['quantidade'] > 5].copy()
            fatos_pequenos = contagem_fatos[contagem_fatos['quantidade'] <= 5].copy()
            
            # Converte os principais para lista de dicionários
            lista_final = fatos_principais.to_dict('records')
            
            # Se houver fatos pequenos, soma tudo e cria uma categoria "DIVERSOS"
            if not fatos_pequenos.empty:
                soma_pequenos = int(fatos_pequenos['quantidade'].sum())
                lista_final.append({'fato': 'DIVERSOS (<= 5)', 'quantidade': soma_pequenos})
            
            # Paginação (mantida caso a lista final ainda fique grande)
            for i in range(0, len(lista_final), 10):
                dados_fatos_paginados.append(lista_final[i:i + 10])

            # --- RESTANTE DO CÓDIGO (Status e Mensal) ---
            contagem_status = df['status'].value_counts()
            status_chart_data = {'labels': contagem_status.index.tolist(), 'data': [int(q) for q in contagem_status.values.tolist()]}
            
            # Cálculo de Médias de Tempo
            df_horas_total = df[df['tempo_total_dp'].notna()].copy()
            def hhmm_para_minutos(valor):
                if isinstance(valor, timedelta): return valor.total_seconds() / 60
                if isinstance(valor, str) and ':' in valor:
                    try:
                        h, m = map(int, valor.split(':')[:2])
                        return h * 60 + m
                    except: return 0
                return 0
            df_horas_total['minutos_dp'] = df_horas_total['tempo_total_dp'].apply(hhmm_para_minutos)
            if not df_horas_total.empty:
                media = df_horas_total['minutos_dp'].mean()
                if pd.notna(media):
                    h, m = divmod(int(media), 60)
                    kpis['media_tempo_dp'] = f"{h:02}:{m:02}"

            # Lógica Mensal
            df['mes'] = df['data_registro'].dt.to_period('M').astype(str)
            meses_unicos = sorted(df['mes'].unique())
            for mes in meses_unicos:
                df_mes = df[df['mes'] == mes]
                contagem = df_mes['fato_agrupado'].value_counts().reset_index()
                contagem.columns = ['fato', 'quantidade']
                if len(contagem) > 3:
                    top_3 = contagem.head(3)
                    outros = contagem.iloc[3:]['quantidade'].sum()
                    labels = top_3['fato'].tolist() + ['OUTROS']
                    data = [int(q) for q in top_3['quantidade'].tolist()] + [int(outros)]
                else:
                    labels = contagem['fato'].tolist()
                    data = [int(q) for q in contagem['quantidade'].tolist()]
                
                df_horas_mes = df_mes[df_mes['tempo_total_dp'].notna()].copy()
                df_horas_mes['minutos_dp'] = df_horas_mes['tempo_total_dp'].apply(hhmm_para_minutos)
                horas_dp = df_horas_mes.groupby('delegacia')['minutos_dp'].sum() / 60
                horas_dp = horas_dp[horas_dp > 0].round(1)
                
                dados_mensais.append({
                    'mes': mes,
                    'top3_fatos': {'labels': labels, 'data': data},
                    'horas_delegacia': {'labels': horas_dp.index.tolist(), 'data': [float(h) for h in horas_dp.values.tolist()]}
                })

    except Exception as e:
        print(f"ERRO DASHBOARD: {e}")
        flash(f"Erro estatísticas: {e}", "danger")
    finally:
        if cursor: cursor.close()

    return render_template('dashboard.html', kpis=kpis, dados_fatos_paginados=dados_fatos_paginados, dados_mensais=dados_mensais, status_chart_data=status_chart_data)

@app.route('/exportar_dashboard')
def exportar_dashboard():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM historico_ocorrencias")
        historico_completo = cursor.fetchall()
        if not historico_completo:
            flash('Sem dados para exportar.', 'info')
            return redirect(url_for('dashboard'))
        
        df = pd.DataFrame(historico_completo)
        # (Limpeza e preparação de dados igual ao dashboard aqui)
        # ...
        # Formatação de Horas para Excel
        colunas_de_horario = ['chegada_delegacia', 'entrega_ro', 'saida_delegacia']
        def formatar_timedelta(td):
            if pd.isnull(td): return ''
            segundos = int(td.total_seconds())
            h, r = divmod(segundos, 3600)
            m, s = divmod(r, 60)
            return f"'{h:02}:{m:02}:{s:02}"
        for col in colunas_de_horario:
            if col in df.columns: df[col] = df[col].apply(formatar_timedelta)

        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, sheet_name='Dados Completos', index=False)
        writer.close()
        output.seek(0)
        nome = f"dashboard_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=nome)
    except Exception as e:
        flash(f"Erro Excel: {e}", "danger")
        return redirect(url_for('dashboard'))
    finally:
        if cursor: cursor.close()

# ROTAS DE GERENCIAMENTO DE FATOS
@app.route('/gerenciar_fatos')
def gerenciar_fatos():
    conn = None
    cursor = None
    fatos = []
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM tipos_fatos ORDER BY nome ASC")
        fatos = cursor.fetchall()
    finally:
        if cursor: cursor.close()
    return render_template('gerenciar_fatos.html', fatos=fatos)

@app.route('/adicionar_fato', methods=['POST'])
def adicionar_fato():
    # Função local de limpeza para garantir que entre limpo no banco
    def limpar_texto_insercao(texto):
        if not isinstance(texto, str): return ''
        texto_sem_acento = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        return texto_sem_acento.strip().upper()

    nome = limpar_texto_insercao(request.form.get('nome', ''))
    
    if nome:
        conn = get_db()
        cursor = conn.cursor()
        try:
            # Verifica se já existe algo parecido
            cursor.execute("SELECT id FROM tipos_fatos WHERE nome = %s", (nome,))
            if cursor.fetchone():
                flash(f'O fato "{nome}" já existe na lista.', 'warning')
            else:
                cursor.execute("INSERT INTO tipos_fatos (nome) VALUES (%s)", (nome,))
                conn.commit()
                flash('Novo fato adicionado, volte e atualize a página de gerenciamento para ver novo crime!', 'success')
        except Exception as e:
            flash(f'Erro ao adicionar: {e}', 'danger')
        finally:
            cursor.close()
    return redirect(url_for('gerenciar_fatos'))

@app.route('/excluir_fato/<int:id>', methods=['POST'])
def excluir_fato(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tipos_fatos WHERE id = %s", (id,))
    conn.commit()
    flash('Fato removido.', 'success')
    return redirect(url_for('gerenciar_fatos'))

@app.route('/popular_fatos')
def popular_fatos():
    senha_digitada = request.form.get('password')
    SENHA_MESTRA = "copomadmin2025" # Mesma senha que você usou no histórico

    if senha_digitada == SENHA_MESTRA:
        conn = get_db()
        cursor = conn.cursor()
    
    # Função local de limpeza para popular
    def limpar_texto_populacao(texto):
        texto_sem_acento = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
        return texto_sem_acento.strip().upper()

    # LISTA INICIAL DE CRIMES (PARA POPULAR O BANCO)
    LISTA_CRIMES_INICIAL = [
        "ART 121   HOMICIDIO",
        "ART 122   INDUZIMENTO INSTIGACAO OU AUXILIO AO SUICIDIO",
        "ART 123   INFANTICIDIO",
        "ART 124   ABORTO PROVOCADO PELA GESTANTE",
        "ART 125   ABORTO PROVOCADO POR TERCEIRO",
        "ART 126   ABORTO SEM CONSENTIMENTO",
        "ART 127   FORMA QUALIFICADA DO ABORTO",
        "ART 129   LESAO CORPORAL",
        "ART 130   PERIGO DE CONTAGIO VENEREO",
        "ART 131   PERIGO DE CONTAGIO DE MOLESTIA GRAVE",
        "ART 132   PERIGO PARA A VIDA OU SAUDE",
        "ART 133   ABANDONO DE INCAPAZ",
        "ART 134   EXPOSICAO OU ABANDONO DE RECEM NASCIDO",
        "ART 135   OMISSAO DE SOCORRO",
        "ART 136   MAUS TRATOS",
        "ART 137   RIXA",
        "ART 138   CALUNIA",
        "ART 139   DIFAMACAO",
        "ART 140   INJURIA",
        "ART 146   CONSTRANGIMENTO ILEGAL",
        "ART 147   AMEACA",
        "ART 148   CARCERE PRIVADO",
        "ART 149   REDUCAO A CONDICAO ANALOGA A DE ESCRAVO",
        "ART 149 A   TRAFICO DE PESSOAS",
        "ART 150   VIOLACAO DE DOMICILIO",
        "ART 151   VIOLACAO DE CORRESPONDENCIA",
        "ART 152   DIVULGACAO INDEVIDA DE CORRESPONDENCIA",
        "ART 155   FURTO",
        "ART 157   ROUBO",
        "ART 158   EXTORSAO",
        "ART 159   EXTORSAO MEDIANTE SEQUESTRO",
        "ART 160   CONSTRANGIMENTO ILEGAL PATRIMONIAL",
        "ART 161   ALTERACAO DE LIMITES",
        "ART 162   ESBULHO POSSESSORIO",
        "ART 163   DANO",
        "ART 164   DANO EM COISA DE USO COMUM",
        "ART 168   APROPRIACAO INDEBITA",
        "ART 169   APROPRIACAO DE COISA ACHADA",
        "ART 171   ESTELIONATO",
        "ART 180   RECEPTACAO",
        "ART 184   VIOLACAO DE DIREITO AUTORAL",
        "ART 197 A 207   CRIMES CONTRA O TRABALHO",
        "ART 208   VILIPENDIO A CULTO",
        "ART 209   PERTURBACAO DE CERIMONIA",
        "ART 210   ULTRAJE A CULTO",
        "ART 211   DESTRUICAO DE SEPULTURA",
        "ART 212   VILIPENDIO A CADAVER",
        "ART 213   ESTUPRO",
        "ART 214   VIOLACAO SEXUAL MEDIANTE FRAUDE",
        "ART 215 A   IMPORTUNACAO SEXUAL",
        "ART 216 A   ASSEDIO SEXUAL",
        "ART 217 A   ESTUPRO DE VULNERAVEL",
        "ART 218   SATISFACAO DE LASCIVIA",
        "ART 218 A   FAVORECIMENTO DA PROSTITUICAO DE MENOR",
        "ART 218 B   EXPLORACAO SEXUAL",
        "ART 250 A 259   INCENDIO EXPLOSAO",
        "ART 267 A 285   CRIMES CONTRA SAUDE PUBLICA",
        "ART 286   INCITACAO AO CRIME",
        "ART 287   APOLOGIA",
        "ART 288   ASSOCIACAO CRIMINOSA",
        "ART 289 A 311   MOEDA FALSA FALSIFICACAO",
        "ART 312   PECULATO",
        "ART 313   INSERCAO DE DADOS FALSOS",
        "ART 316   CONCUSSAO",
        "ART 317   CORRUPCAO PASSIVA",
        "ART 318   FACILITACAO DE CONTRABANDO",
        "ART 319   PREVARICACAO",
        "ART 320   CONDESCENDENCIA CRIMINOSA",
        "ART 321   ADVOCACIA ADMINISTRATIVA",
        "ART 330   DESOBEDIENCIA",
        "ART 331   DESACATO",
        "ART 333   CORRUPCAO ATIVA",
        "ART 334   CONTRABANDO",
        "ART 334 A   DESCAMINHO",
        "ART 339   DENUNCIACAO CALUNIOSA",
        "ART 340   COMUNICACAO FALSA DE CRIME",
        "ART 342   FALSO TESTEMUNHO",
        "ART 347   FRAUDE PROCESSUAL",
        "DESCUMPRIMENTO DE MEDIDA PROTETIVA",
        "MANDADO DE PRISAO",
        "VIAS DE FATO",
        "TRAFICO DE DROGAS",
        "CRIME CONTRA CRIANCA E ADOLESCENTE ECA",
        "SUICIDIO",
        "EMBRIAGUES AO VOLANTE",
        "ADULTERACAO DE SINAL IDENTIFICADOR",
        "DIRECAO PERIGOSA",
        "EVASAO"
    ]

    for crime in LISTA_CRIMES_INICIAL:
        crime_limpo = limpar_texto_populacao(crime)
        cursor.execute("SELECT id FROM tipos_fatos WHERE nome = %s", (crime_limpo,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO tipos_fatos (nome) VALUES (%s)", (crime_limpo,))
    
    conn.commit()
    flash('Lista populada com sucesso (nomes padronizados sem acentos)!', 'success')
    return redirect(url_for('gerenciar_fatos'))

# 📄 Rota para EXPORTAR O RELATÓRIO DE OCORRÊNCIAS (Excel) - REINCLUÍDA
@app.route('/exportar_relatorio_excel')
def exportar_relatorio_excel():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        # Busca todas as ocorrências para o relatório
        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY data_registro DESC")
        ocorrencias = cursor.fetchall()

        if not ocorrencias:
            flash('Não há dados para exportar para Excel.', 'info')
            return redirect(url_for('gerenciar_ocorrencias'))

        df = pd.DataFrame(ocorrencias)
        
        # --- BLOCO DE FORMATAÇÃO DE HORÁRIOS (Para evitar erro no Excel) ---
        colunas_de_horario = ['chegada_delegacia', 'entrega_ro', 'saida_delegacia']
        
        def formatar_timedelta_para_hora(td):
            if pd.isnull(td): return ''
            # Se for string, tenta manter ou limpar
            if isinstance(td, str): return td
            # Se for timedelta, converte
            segundos_totais = int(td.total_seconds())
            horas, resto = divmod(segundos_totais, 3600)
            minutos, segundos = divmod(resto, 60)
            return f"'{horas:02}:{minutos:02}:{segundos:02}"

        for coluna in colunas_de_horario:
            if coluna in df.columns:
                df[coluna] = df[coluna].apply(formatar_timedelta_para_hora)
        # -------------------------------------------------------------------

        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='Ocorrencias')
        writer.close()
        output.seek(0)

        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name='relatorio_ocorrencias_cepol.xlsx')

    except Exception as e:
        flash(f"Erro ao gerar Excel: {e}", 'danger')
        return redirect(url_for('gerenciar_ocorrencias'))
    finally:
        if cursor:
            cursor.close()

if __name__ == '__main__':
    app.run(debug=True)