# Seu topo do arquivo, garantindo que 'tempfile' e 'os' estejam importados
from dotenv import load_dotenv
load_dotenv() # Carrega as variáveis de ambiente do .env
import os
import MySQLdb
from flask import Flask, render_template, request, redirect, url_for, flash, g
from datetime import datetime, timedelta, time
import pandas as pd
from flask import send_file
from io import BytesIO
import tempfile # <--- Importe tempfile aqui!

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'sua-chave-secreta-para-desenvolvimento-local')

# --- Funções para Gerenciar a Conexão com o Banco de Dados ---
def get_db():
    """Obtém uma conexão de banco de dados por requisição."""
    if 'db' not in g:
        db_host = os.environ.get('DB_HOST')
        db_port = int(os.environ.get('DB_PORT', 4000))
        db_user = os.environ.get('DB_USER')
        db_password = os.environ.get('DB_PASSWORD')
        db_name = os.environ.get('DB_NAME')
        ca_cert_content = os.environ.get('CA_CERT_CONTENT')

        # Linhas de DEBUG (Mantenha para testar, remova ou comente depois)
        print(f"DEBUG: DB_HOST={db_host}")
        print(f"DEBUG: DB_PORT={db_port}")
        print(f"DEBUG: DB_USER={db_user}")
        print(f"DEBUG: DB_NAME={db_name}")

        # Inicializa ca_path como None, para ser usado na conexão
        ca_path = None

        if ca_cert_content:
            temp_ca_file = tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8')
            temp_ca_file.write(ca_cert_content)
            temp_ca_file.close()
            ca_path = temp_ca_file.name
            print(f"DEBUG: Usando certificado CA temporário: {ca_path}")
        else:
            local_ca_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ca.pem')
            if os.path.exists(local_ca_path):
                ca_path = local_ca_path
                print(f"DEBUG: Usando certificado CA local: {ca_path}")
            else:
                print("DEBUG: Nenhum certificado CA encontrado ou fornecido. A conexão SSL pode falhar.")

        # Conecta ao banco de dados com os parâmetros SSL
        # Note a mudança na forma como 'ssl_mode' e 'ssl' são passados
        g.db = MySQLdb.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            passwd=db_password, # Use 'passwd' para MySQLdb
            db=db_name,         # Use 'db' para MySQLdb
            ssl_mode='VERIFY_IDENTITY',
            ssl={'ca': ca_path} if ca_path else {} # Passa 'ca' dentro do dicionário 'ssl'
        )
    return g.db

# ... (Restante do seu app.py) ...

# SEU CÓDIGO TERÁ ISSO:

@app.teardown_appcontext
def close_db(e=None):
    """Fecha a conexão do banco de dados ao final da requisição."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        # NADA, ABSOLUTAMENTE NADA MAIS VAI AQUI DENTRO.
        # NEM "with app.app_context():" E NEM "def ensure_supervisores_table_and_initial_entry()"

        # --- AQUI VAI A DEFINIÇÃO COMPLETA DA FUNÇÃO ensure_supervisores_table_and_initial_entry() ---
def ensure_supervisores_table_and_initial_entry():
    conn = None
    cursor = None
    print("DEBUG: Iniciando ensure_supervisores_table_and_initial_entry()")
    try:
        conn = get_db()
        cursor = conn.cursor()
        # Cria a tabela 'supervisores' se ela não existir
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS supervisores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                supervisor_operacoes VARCHAR(100) DEFAULT '',
                coordenador VARCHAR(100) DEFAULT '',
                supervisor_despacho VARCHAR(100) DEFAULT '',
                coordenador_plantao VARCHAR(100) DEFAULT '',
                supervisor_atendimento VARCHAR(100) DEFAULT '',
                last_updated DATETIME
            )
        """)
        conn.commit()
        print("DEBUG: Tabela 'supervisores' verificada/criada.")

        cursor.execute("SELECT COUNT(*) FROM supervisores")
        count = cursor.fetchone()[0]
        print(f"DEBUG: Contagem atual de supervisores: {count}")

        if count == 0:
            print("DEBUG: Tabela 'supervisores' vazia, inserindo entrada inicial.")
            cursor.execute("""
                INSERT INTO supervisores (id, supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento, last_updated)
                VALUES (1, '', '', '', '', NOW())
            """)
            conn.commit()
            print("DEBUG: Entrada inicial para a tabela 'supervisores' criada com sucesso.")
        else:
            print("DEBUG: Tabela 'supervisores' já existe e possui entradas.")
    except MySQLdb.Error as err:
        print(f"DEBUG: Erro ao inicializar a tabela 'supervisores': {err}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()

# --- AQUI VAI A CHAMADA PARA A FUNÇÃO (DEPOIS DA DEFINIÇÃO DELA) ---
with app.app_context():
    ensure_supervisores_table_and_initial_entry()

# Função auxiliar para formatar minutos para HH:MM
def format_minutes_to_hh_mm(total_minutes):
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"

# Função para converter string "X min" de volta para minutos (se for o caso)
def parse_minutes_from_string(time_str):
    if time_str and isinstance(time_str, str) and " min" in time_str:
        try:
            return int(time_str.replace(" min", "").strip())
        except ValueError:
            pass
    return None # Não é um formato "X min" válido ou erro na conversão

# Função para garantir que o valor do tempo esteja em HH:MM para exibição
def ensure_hh_mm_format_for_display(time_value):
    # Se já é um datetime.time object (ex: se DB column for TIME)
    if isinstance(time_value, time):
        return time_value.strftime("%H:%M")

    # Se já é uma string HH:MM válida (ex: de novas entradas)
    if isinstance(time_value, str) and len(time_value) == 5 and ':' in time_value:
        try:
            datetime.strptime(time_value, "%H:%M")
            return time_value
        except ValueError:
            pass # Não é um HH:MM válido, tenta outras opções

    # Se está no formato "X min" (de entradas antigas), converte e formata
    minutes = parse_minutes_from_string(time_value)
    if minutes is not None:
        return format_minutes_to_hh_mm(minutes) # Usa o formatter existente

    return '' # Retorna string vazia para qualquer outro caso inválido/vazio

# 🔧 Status disponíveis (CORRIGIDO: 'FORÇA TATICA' com espaço)
STATUS_OPTIONS = [
    'ADM', 'CFP', 'FORÇA TATICA', 'RP', 'TRANSITO', 'ADJ CFP', 'INTERIOR',
    'MOTO', 'ROTAC', 'CANIL', 'BOPE', 'ESCOLAR/PROMUSE', 'POL.COMUNITARIO',
    'JUIZADO', 'TRANSITO/BLITZ'
]

# Função para garantir que a tabela 'supervisores' exista e tenha uma entrada inicial
def ensure_supervisores_table_and_initial_entry(): # Indentação corrigida aqui
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS supervisores (
                id INT AUTO_INCREMENT PRIMARY KEY,
                supervisor_operacoes VARCHAR(100) DEFAULT '',
                coordenador VARCHAR(100) DEFAULT '',
                supervisor_despacho VARCHAR(100) DEFAULT '',
                supervisor_atendimento VARCHAR(100) DEFAULT '',
                last_updated DATETIME
            )
        """)
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM supervisores")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO supervisores (id, supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento, last_updated)
                VALUES (1, '', '', '', '', NOW())
            """)
            conn.commit()
            print("Entrada inicial para a tabela 'supervisores' criada com sucesso.")
        else:
            print("Tabela 'supervisores' já existe e possui entradas.")
    # Exceção corrigida para MySQLdb.Error
    except MySQLdb.Error as err:
        print(f"Erro ao inicializar a tabela 'supervisores': {err}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        # conn.close() é tratado por @app.teardown_appcontext, não precisa aqui

# A chamada a ensure_supervisores_table_and_initial_entry() foi movida para o if __name__ == '__main__':

# --- FIM DO NOVO CÓDIGO PARA SUPERVISORES ---

# 🔵 Página principal (ROTA INDEX EXISTENTE, AGORA MODIFICADA PARA INCLUIR SUPERVISORES)
@app.route('/', methods=['GET', 'POST'])
def index():
    conn = None
    cursor = None
    supervisores_data = {
        'supervisor_operacoes': '', 'coordenador': '',
        'supervisor_despacho': '', 'supervisor_atendimento': '',
        'last_updated': None
    }
    unidades = []
    viaturas = []
    contatos = [] # Alterado de 'cfps' para 'contatos' para consistência

    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor) # <--- MODIFIQUE ESTA LINHA!

        # --- Lógica de POST para Supervisores ---
        if request.method == 'POST' and 'supervisorOperacoes' in request.form:
            supervisor_operacoes = request.form.get('supervisorOperacoes', '')
            coordenador = request.form.get('coordenador', '')
            supervisor_despacho = request.form.get('supervisorDespacho', '')
            supervisor_atendimento = request.form.get('supervisorAtendimento', '')
            current_time = datetime.now()

            sql_update = """
                UPDATE supervisores SET
                supervisor_operacoes = %s,
                coordenador = %s,
                supervisor_despacho = %s,
                supervisor_atendimento = %s,
                last_updated = %s
                WHERE id = 1
            """
            cursor.execute(sql_update, (supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento, current_time))
            conn.commit()
            flash('Supervisores salvos com sucesso!', 'success')
            return redirect(url_for('index'))

        # --- Lógica de POST para Contato (era CFP, agora 'contatos') ---
        elif request.method == 'POST' and request.form.get('tipo') == 'contato': # Assumindo que o formulário de contato tenha um campo 'tipo'='contato'
            unidade_id = request.form.get('unidade')
            nome_cfp = request.form.get('nome') # Nome do CFP
            telefone = request.form.get('telefone')

            # Verifica se já existe um contato para essa unidade_id
            cursor.execute("SELECT * FROM contatos WHERE unidade_id=%s", (unidade_id,))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE contatos SET cfp=%s, telefone=%s WHERE unidade_id=%s", # 'cfp' é o nome da coluna para o nome do CFP
                    (nome_cfp, telefone, unidade_id)
                )
            else:
                cursor.execute(
                    "INSERT INTO contatos (unidade_id, cfp, telefone) VALUES (%s, %s, %s)",
                    (unidade_id, nome_cfp, telefone)
                )
            conn.commit()
            flash('Contato salvo com sucesso!', 'success')
            return redirect(url_for('index'))

        # --- Lógica de GET para Supervisores ---
        cursor.execute("SELECT * FROM supervisores WHERE id = 1")
        row_supervisores = cursor.fetchone()
        if row_supervisores:
            supervisores_data = row_supervisores

        # --- Lógica de GET para Unidades, Viaturas, Contatos ---
        cursor.execute("SELECT * FROM unidades")
        unidades = cursor.fetchall()

        cursor.execute("""
                       SELECT v.id, v.prefixo, v.unidade_id, v.status, u.nome_unidade AS unidade_nome
                       FROM viaturas v JOIN unidades u ON v.unidade_id = u.id
                       ORDER BY u.nome_unidade, v.prefixo
                       """)
        viaturas_data = cursor.fetchall()
        viaturas = viaturas_data # CORRIGIDO: Atribui os dados corretamente

        cursor.execute("""
            SELECT c.*, u.nome_unidade AS unidade_nome
            FROM contatos c JOIN unidades u ON c.unidade_id = u.id
        """)
        contatos = cursor.fetchall() # Alterado de 'cfps' para 'contatos'

    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Database error: {err}", 'danger')
        unidades = []
        viaturas = []
        contatos = [] # Alterado de 'cfps' para 'contatos'
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return render_template('index.html', unidades=unidades, status_options=STATUS_OPTIONS,
                           viaturas=viaturas, contatos=contatos, supervisores=supervisores_data) # Alterado de 'cfps' para 'contatos'

# 🚗 Cadastro de viaturas
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
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            unidade_id = request.form['unidade_id']
            prefixo = request.form['prefixo']
            status = request.form['status']
            hora_entrada = request.form.get('hora_entrada')
            hora_saida = request.form.get('hora_saida')

            cursor.execute(
                "SELECT * FROM viaturas WHERE prefixo = %s AND unidade_id = %s",
                (prefixo, unidade_id)
            )
            existente = cursor.fetchone()

            if existente:
                flash('Esta viatura já está cadastrada nesta unidade!', 'warning')
            else:
                cursor.execute("""
                    INSERT INTO viaturas (unidade_id, prefixo, status, hora_entrada, hora_saida)
                    VALUES (%s, %s, %s, %s, %s)
                """, (unidade_id, prefixo, status, hora_entrada, hora_saida))
                conn.commit()
                flash('Viatura cadastrada com sucesso!', 'success')

            return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

        cursor.execute("SELECT id, nome_unidade AS nome FROM unidades")
        unidades = cursor.fetchall()

        if unidade_filtro:
            cursor.execute("""
                SELECT v.id, u.nome_unidade AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
                FROM viaturas v
                JOIN unidades u ON v.unidade_id = u.id
                WHERE v.unidade_id = %s
            """, (unidade_filtro,))
        else:
            cursor.execute("""
                SELECT v.id, u.nome_unidade AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
                FROM viaturas v
                JOIN unidades u ON v.unidade_id = u.id
                ORDER BY u.nome_unidade ASC, v.prefixo ASC
            """)
        viaturas = cursor.fetchall()

        cursor.execute("""
            SELECT unidade_id, COUNT(*) as quantidade
            FROM viaturas
            GROUP BY unidade_id
        """)
        contagem_viaturas_por_unidade = {row['unidade_id']: row['quantidade'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT c.id, u.nome_unidade AS unidade_nome, c.cfp, c.telefone
            FROM contatos c
            JOIN unidades u ON c.unidade_id = u.id
        """)
        contatos = cursor.fetchall()

    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Database error loading vehicles: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return render_template(
        'cadastro_viaturas.html',
        unidades=unidades,
        viaturas=viaturas,
        contatos=contatos,
        unidade_filtro=unidade_filtro,
        contagem_viaturas_por_unidade=contagem_viaturas_por_unidade
    )

@app.route('/exportar_relatorio_excel')
def exportar_relatorio_excel():
    conn = None
    cursor = None
    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)  # Retorna dicionários para fácil conversão em DataFrame

        # Exemplo: Buscar todas as ocorrências. Ajuste esta query se o seu relatório for diferente.
        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY data_registro DESC")
        ocorrencias = cursor.fetchall()

        if not ocorrencias:
            flash('Não há dados para exportar para Excel.', 'info')
            return redirect(url_for('relatorios'))  # Redirecione para a sua página de relatório (mude o nome se for diferente)

        # Converter a lista de dicionários em um DataFrame do pandas
        df = pd.DataFrame(ocorrencias)

        # Definir o caminho para salvar o arquivo temporariamente
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='Ocorrencias')
        writer.close()
        output.seek(0)

        # Enviar o arquivo para download
        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name='relatorio_ocorrencias_cepol.xlsx')

    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Erro no banco de dados ao exportar: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado ao exportar: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    # Em caso de erro, redirecione para a página de relatório
    return redirect(url_for('relatorios')) # Mude para a rota da sua página de relatório (se for diferente)

@app.route('/editar_contato/<int:contato_id>', methods=['GET'])
def editar_contato(contato_id):
    conn = None
    cursor = None
    contato = None
    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT * FROM contatos WHERE id = %s", (contato_id,))
        contato = cursor.fetchone()
    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Database error: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    if contato is None:
        flash('Contato não encontrado.', 'danger')
        return redirect(url_for('cadastro_viaturas'))

    return render_template('editar_contato.html', contato=contato)

@app.route('/editar_contato/<int:contato_id>', methods=['POST'])
def editar_contato_post(contato_id):
    conn = None
    cursor = None
    unidade_id = request.form['unidade_id'] # Mantido, assumindo que vem do formulário
    try:
        unidade_id = request.form['unidade_id']
        cfp = request.form['cfp']
        telefone = request.form['telefone']

        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE contatos
            SET unidade_id = %s, cfp = %s, telefone = %s
            WHERE id = %s
        """, (unidade_id, cfp, telefone, contato_id))

        conn.commit()
        flash('Contato atualizado com sucesso!', 'success')
    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Database error updating contact: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

# ➕ Adicionar contato
@app.route('/adicionar_contato', methods=['POST'])
def adicionar_contato():
    conn = None
    cursor = None
    unidade_id = request.form.get('unidade_id', '') # Mantido, pode ser usado para redirecionamento

    try:
        unidade_id = request.form['unidade_id']
        cfp = request.form['cfp']
        telefone = request.form['telefone']

        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO contatos (unidade_id, cfp, telefone)
            VALUES (%s, %s, %s)
        """, (unidade_id, cfp, telefone))

        conn.commit()
        flash('Contato cadastrado com sucesso!', 'success')
    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Database error adding contact: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

# ❌ Excluir contato
@app.route('/excluir_contato/<int:contato_id>', methods=['POST'])
def excluir_contato(contato_id):
    conn = None
    cursor = None
    unidade_id = ''

    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        cursor.execute("SELECT unidade_id FROM contatos WHERE id = %s", (contato_id,))
        contato = cursor.fetchone()
        unidade_id = contato['unidade_id'] if contato else ''

        cursor.execute("DELETE FROM contatos WHERE id = %s", (contato_id,))
        conn.commit()
        flash('Contato excluído com sucesso!', 'success')
    except MySQLdb.Error as err: # Exceção corrigida
        flash(f'Database error deleting contact: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

# ❌ Excluir viatura
@app.route('/excluir_viatura/<int:viatura_id>', methods=['POST'])
def excluir_viatura(viatura_id):
    conn = None
    cursor = None
    unidade_id = ''

    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
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
    except MySQLdb.Error as err: # Exceção corrigida
        flash(f'Database error deleting vehicle: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

# ✏️ Editar viatura
@app.route('/editar_viatura/<int:viatura_id>', methods=['GET', 'POST'])
def editar_viatura(viatura_id):
    conn = None
    cursor = None
    viatura = None
    unidades = []
    unidade_id_for_redirect = ''

    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            unidade_id_for_redirect = request.form['unidade_id']
            prefixo = request.form['prefixo']
            status = request.form['status']
            hora_entrada = request.form.get('hora_entrada')
            hora_saida = request.form.get('hora_saida')

            cursor.execute("""
                UPDATE viaturas
                SET unidade_id = %s, prefixo = %s, status = %s, hora_entrada = %s, hora_saida = %s
                WHERE id = %s
            """, (unidade_id_for_redirect, prefixo, status, hora_entrada, hora_saida, viatura_id))

            conn.commit()
            flash('Viatura atualizada com sucesso!', 'success')
            return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id_for_redirect))

        cursor.execute("""
            SELECT v.id, v.unidade_id, u.nome_unidade AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
            FROM viaturas v
            JOIN unidades u ON v.unidade_id = u.id
            WHERE v.id = %s
        """, (viatura_id,))
        viatura = cursor.fetchone()

        cursor.execute("SELECT id, nome FROM unidades")
        unidades = cursor.fetchall()

    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Database error editing vehicle: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    if viatura:
        return render_template('editar_viatura.html', viatura=viatura, unidades=unidades)
    else:
        flash('Viatura não encontrada.', 'danger')
        return redirect(url_for('cadastro_viaturas'))

# --- ROTAS PARA OCORRÊNCIAS CEPOL ---
# 📝 Rota principal para Gerenciar Ocorrências
@app.route('/ocorrencias', methods=['GET', 'POST'])
def gerenciar_ocorrencias():
    conn = None
    cursor = None
    ocorrencias = []

    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            fato = request.form.get('fato', '').strip()
            status = request.form.get('status', '').strip()
            protocolo = request.form.get('protocolo', '').strip()
            ro_cadg = request.form.get('ro_cadg', '').strip()
            chegada = request.form.get('chegada', '').strip()
            entrega_ro = request.form.get('entrega_ro', '').strip()
            saida = request.form.get('saida', '').strip()

            if not all([fato, status, protocolo, ro_cadg, chegada, entrega_ro, saida]):
                flash('Preencha todos os campos obrigatórios!', 'danger')
                return redirect(url_for('gerenciar_ocorrencias'))

            fmt = "%H:%M"
            try:
                chegada_dt = datetime.strptime(chegada, fmt)
                entrega_dt = datetime.strptime(entrega_ro, fmt)
                saida_dt = datetime.strptime(saida, fmt)
            except ValueError:
                flash('Formato de horário inválido. Utilize HH:MM.', 'danger')
                return redirect(url_for('gerenciar_ocorrencias'))

            if saida_dt < chegada_dt:
                saida_dt += timedelta(days=1)
            if entrega_dt < chegada_dt:
                entrega_dt += timedelta(days=1)

            tempo_total_min = int((saida_dt - chegada_dt).total_seconds() // 60)
            tempo_entrega_min = int((entrega_dt - chegada_dt).total_seconds() // 60)

            tempo_total_dp = format_minutes_to_hh_mm(tempo_total_min)
            tempo_entrega_dp = format_minutes_to_hh_mm(tempo_entrega_min)

            cursor.execute("""
                INSERT INTO ocorrencias_cepol
                (fato, status, protocolo, ro_cadg, chegada_delegacia, entrega_ro, saida_delegacia,
                 tempo_total_dp, tempo_entrega_dp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (fato, status, protocolo, ro_cadg, chegada, entrega_ro, saida,
                  tempo_total_dp, tempo_entrega_dp))

            conn.commit()
            flash('Ocorrência registrada com sucesso!', 'success')
            return redirect(url_for('gerenciar_ocorrencias'))

        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY id DESC")
        ocorrencias = cursor.fetchall()

    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Erro no banco de dados ao gerenciar ocorrências: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return render_template('ocorrencias_cepol.html', ocorrencias=ocorrencias)

# 🗑️ Rota para excluir ocorrência
@app.route('/excluir_ocorrencia/<int:id>', methods=['POST'])
def excluir_ocorrencia(id):
    conn = None
    cursor = None
    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ocorrencias_cepol WHERE id = %s", (id,))
        conn.commit()
        flash('Ocorrência excluída com sucesso!', 'success')
    except MySQLdb.Error as err: # Exceção corrigida
        flash(f'Erro ao excluir ocorrência: {err}', 'danger')
    except Exception as e:
        flash(f'Ocorreu um erro inesperado ao excluir: {e}', 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return redirect(url_for('gerenciar_ocorrencias'))

# ✏️ Rota para editar ocorrência
@app.route('/editar_ocorrencia/<int:id>', methods=['GET', 'POST'])
def editar_ocorrencia(id):
    conn = None
    cursor = None
    ocorrencia = None
    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            fato = request.form.get('fato', '').strip()
            status = request.form.get('status', '').strip()
            protocolo = request.form.get('protocolo', '').strip()
            ro_cadg = request.form.get('ro_cadg', '').strip()
            chegada = request.form.get('chegada', '').strip()
            entrega_ro = request.form.get('entrega_ro', '').strip()
            saida = request.form.get('saida', '').strip()

            if not all([fato, status, protocolo, ro_cadg, chegada, entrega_ro, saida]):
                flash('Preencha todos os campos obrigatórios!', 'danger')
                return redirect(url_for('editar_ocorrencia', id=id))

            fmt = "%H:%M"
            try:
                chegada_dt = datetime.strptime(chegada, fmt)
                entrega_dt = datetime.strptime(entrega_ro, fmt)
                saida_dt = datetime.strptime(saida, fmt)
            except ValueError:
                flash('Formato de horário inválido. Utilize HH:MM.', 'danger')
                return redirect(url_for('editar_ocorrencia', id=id))

            if saida_dt < chegada_dt:
                saida_dt += timedelta(days=1)
            if entrega_dt < chegada_dt:
                entrega_dt += timedelta(days=1)

            tempo_total_min = int((saida_dt - chegada_dt).total_seconds() // 60)
            tempo_entrega_min = int((entrega_dt - chegada_dt).total_seconds() // 60)

            # A FUNÇÃO 'format_minutes_to_hh_mm' JÁ ESTÁ DEFINIDA NO TOPO
            tempo_total_dp = format_minutes_to_hh_mm(tempo_total_min)
            tempo_entrega_dp = format_minutes_to_hh_mm(tempo_entrega_min)

            cursor.execute("""
                UPDATE ocorrencias_cepol
                SET fato=%s, status=%s, protocolo=%s, ro_cadg=%s, chegada_delegacia=%s,
                    entrega_ro=%s, saida_delegacia=%s, tempo_total_dp=%s, tempo_entrega_dp=%s
                WHERE id = %s
            """, (fato, status, protocolo, ro_cadg, chegada, entrega_ro, saida,
                  tempo_total_dp, tempo_entrega_dp, id))
            conn.commit()
            flash('Ocorrência atualizada com sucesso!', 'success')
            return redirect(url_for('gerenciar_ocorrencias'))

        # BUSCA DA OCORRÊNCIA (APENAS UMA VEZ)
        cursor.execute("SELECT * FROM ocorrencias_cepol WHERE id = %s", (id,))
        ocorrencia = cursor.fetchone()

        if not ocorrencia:
            flash('Ocorrência não encontrada.', 'danger')
            return redirect(url_for('gerenciar_ocorrencias'))

        # A FUNÇÃO 'ensure_hh_mm_format_for_display' JÁ ESTÁ DEFINIDA NO TOPO
        ocorrencia['chegada_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('chegada_delegacia'))
        ocorrencia['entrega_ro'] = ensure_hh_mm_format_for_display(ocorrencia.get('entrega_ro'))
        ocorrencia['saida_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('saida_delegacia'))

    except MySQLdb.Error as err: # Exceção corrigida
        flash(f"Erro no banco de dados ao carregar/atualizar: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        # conn.close() removido

    return render_template('editar_ocorrencia.html', ocorrencia=ocorrencia)

    # 💣 NOVA Rota para LIMPAR TODAS AS OCORRÊNCIAS
@app.route('/limpar_todas_ocorrencias', methods=['POST'])
def limpar_todas_ocorrencias():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        # EXECUTAR O COMANDO DELETE PARA TODAS AS OCORRÊNCIAS
        cursor.execute("DELETE FROM ocorrencias_cepol")
        conn.commit()
        flash('Todas as ocorrências foram apagadas com sucesso!', 'success')
    except MySQLdb.Error as err:
        flash(f'Erro no banco de dados ao apagar todas as ocorrências: {err}', 'danger')
    except Exception as e:
        flash(f'Ocorreu um erro inesperado ao apagar tudo: {e}', 'danger')
    finally:
        if cursor:
            cursor.close()
            # conn.close() é gerenciado por @app.teardown_appcontext

    return redirect(url_for('gerenciar_ocorrencias'))

# --- Rota para Relatórios ---
@app.route('/relatorios')
def relatorios():
    conn = None
    cursor = None

    supervisores_string = ""
    cfps_data = []
    viaturas_data = []
    viaturas_por_unidade = []
    viaturas_por_status = []
    totais_viaturas = {}

    try:
        conn = get_db() # Substituído get_db_connection() por get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        # 1. Supervisores de Serviço (para exibição em uma única linha no relatório)
        cursor.execute("""
                       SELECT supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento
                       FROM supervisores
                       WHERE id = 1
                       """)
        supervisores_db_row = cursor.fetchone()

        if supervisores_db_row:
            supervisores_parts = []
            if supervisores_db_row['supervisor_operacoes']:
                supervisores_parts.append(f"<strong>Supervisor de Operações:</strong> {supervisores_db_row['supervisor_operacoes']}")
            if supervisores_db_row['coordenador']:
                supervisores_parts.append(f"<strong>Coordenador:</strong> {supervisores_db_row['coordenador']}")
            if supervisores_db_row['supervisor_despacho']:
                supervisores_parts.append(f"<strong>Supervisor de Despacho:</strong> {supervisores_db_row['supervisor_despacho']}")
            if supervisores_db_row['supervisor_atendimento']:
                supervisores_parts.append(f"<strong>Supervisor de Atendimento:</strong> {supervisores_db_row['supervisor_atendimento']}")
            if supervisores_parts:
                supervisores_string = " - ".join(supervisores_parts)
            else:
                supervisores_string = "Nenhum supervisor configurado."
        else:
            supervisores_string = "Nenhum supervisor cadastrado."

        # 2. Contatos/CFPs Cadastrados
        cursor.execute("""
                       SELECT c.id, c.unidade_id, c.cfp AS nome, c.telefone, u.nome_unidade AS unidade_nome
                       FROM contatos c
                                JOIN unidades u ON c.unidade_id = u.id
                       ORDER BY u.nome_unidade, c.cfp
                       """)
        cfps_data = cursor.fetchall()

        # 3. Viaturas Cadastradas
        cursor.execute("""
                       SELECT v.*, u.nome_unidade AS unidade_nome
                       FROM viaturas v
                                JOIN unidades u ON v.unidade_id = u.id
                       ORDER BY u.nome_unidade, v.prefixo
                       """)
        viaturas_data = cursor.fetchall()

        # 4. Quantidade de Viaturas por Unidade
        cursor.execute("""
                       SELECT u.nome_unidade AS unidade_nome, COUNT(v.id) AS quantidade
                       FROM viaturas v
                                JOIN unidades u ON v.unidade_id = u.id
                       GROUP BY u.nome_unidade
                       ORDER BY u.nome_unidade
                       """)
        viaturas_por_unidade = cursor.fetchall()

        # 5. Quantidade de Viaturas por Status
        cursor.execute("""
                       SELECT status, COUNT(id) AS quantidade
                       FROM viaturas
                       GROUP BY status
                       ORDER BY status
                       """)
        viaturas_por_status = cursor.fetchall()

        # 6. Tabela Específica para Funções de Viaturas (totais por tipo, baseado em STATUS)
        cursor.execute("""
                       SELECT SUM(CASE
                                      WHEN status IN
                                           ('ADM', 'CFP', 'FORÇA TATICA', 'RP', 'TRANSITO', 'ADJ CFP', 'INTERIOR',
                                            'MOTO', 'ROTAC', 'CANIL', 'BOPE', 'ESCOLAR/PROMUSE', 'POL.COMUNITARIO',
                                            'JUIZADO', 'TRANSITO/BLITZ') THEN 1
                                      ELSE 0 END)                                                           AS total_viaturas_geral,
                              SUM(CASE WHEN status = 'INTERIOR' THEN 1 ELSE 0 END)                          AS total_interior,
                              SUM(CASE WHEN status = 'MOTO' THEN 1 ELSE 0 END)                              AS total_motos,
                              SUM(CASE WHEN status IN ('FORÇA TATICA', 'RP', 'TRANSITO') THEN 1 ELSE 0 END) AS soma_atendimento_copom
                       FROM viaturas;
                       """)
        totais_viaturas_row = cursor.fetchone()

        # Calcular a soma total de CAPITAL + INTERIOR + MOTOS no Python
        # Note: 'total_viaturas_geral' já inclui todas as viaturas (Capital, Interior, Motos, etc.)
        # Então, 'total_capital_interior_motos' deve ser apenas o 'total_viaturas_geral'
        # ou, se a intenção é somar capital (que não é interior nem moto), com interior e motos,
        # precisamos de uma categoria explícita para "capital" que não seja interior ou moto.
        # Por enquanto, vou assumir que 'total_viaturas_geral' já é a soma total de todas as viaturas
        # que entram na lista de STATUS_OPTIONS.
        if totais_viaturas_row:
            totais_viaturas = {
                'total_viaturas_geral': totais_viaturas_row['total_viaturas_geral'],
                'total_interior': totais_viaturas_row['total_interior'],
                'total_motos': totais_viaturas_row['total_motos'],
                'soma_atendimento_copom': totais_viaturas_row['soma_atendimento_copom']
            }
            # Se 'total_viaturas_geral' já é o total de todas as viaturas válidas,
            # não precisamos somar novamente 'total_interior' e 'total_motos' a ele para um "total geral".
            # Se a ideia era separar CAPITAL, INTERIOR e MOTOS e depois somá-los,
            # a query SQL precisaria ser mais específica para CAPITAL.
            # Por agora, 'total_capital_interior_motos' será igual a 'total_viaturas_geral'
            # (assumindo que 'total_viaturas_geral' é de fato o total de todas as viaturas relevantes).
            # Se você tem uma definição diferente para "capital", me avise.
            totais_viaturas['total_capital_interior_motos'] = totais_viaturas_row['total_viaturas_geral']
        else:
            # Caso não haja viaturas, inicializa com zeros
            totais_viaturas = {
                'total_viaturas_geral': 0, 'total_interior': 0, 'total_motos': 0,
                'soma_atendimento_copom': 0, 'total_capital_interior_motos': 0
            }

        # EXCEÇÃO CORRIGIDA PARA MySQLdb.Error
    except MySQLdb.Error as err:
        flash(f"Erro no banco de dados ao carregar relatórios: {err}", 'danger')
        # Em caso de erro, inicializa todas as variáveis para evitar "NameError" no template
        supervisores_string = "Erro ao carregar supervisores."
        cfps_data = []  # Mantenha o nome 'cfps_data' aqui
        viaturas_data = []
        viaturas_por_unidade = []
        viaturas_por_status = []
        totais_viaturas = {}
    finally:
        if cursor:
            cursor.close()
        # Removido 'if conn: conn.close()' pois 'g.db' é fechado por @app.teardown_appcontext

        # FINAL DA FUNÇÃO: Retorna o template com TODAS as variáveis
    return render_template('relatorios.html',
                           supervisores_string=supervisores_string,
                           cfps=cfps_data,  # Renomeado para 'cfps' para o template
                           viaturas=viaturas_data,
                           viaturas_por_unidade=viaturas_por_unidade,
                           viaturas_por_status=viaturas_por_status,
                           totais_viaturas=totais_viaturas)


# ... (restante do seu app.py, incluindo app.run(debug=True)

# ESTE BLOCO DEVE ESTAR NO FINAL DO SEU ARQUIVO
if __name__ == '__main__':
    app.run(debug=True)