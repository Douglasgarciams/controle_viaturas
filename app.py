# Seu topo do arquivo, garantindo que 'tempfile' e 'os' estejam importados
from dotenv import load_dotenv
load_dotenv() # Carrega as variáveis de ambiente do .env
import os
import MySQLdb
import pytz
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

            # --- CORREÇÃO AQUI ---
            # Define o fuso horário de Mato Grosso do Sul
            fuso_horario_ms = pytz.timezone('America/Campo_Grande')
            # Pega a data e hora ATUAL neste fuso horário
            current_time = datetime.now(fuso_horario_ms)
            # --- FIM DA CORREÇÃO ---

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

@app.route('/cadastro_viaturas', methods=['GET', 'POST'])
def cadastro_viaturas():
    conn = None
    cursor = None
    unidades = []
    viaturas = []
    contatos = [] # Adicionado para evitar erro se não for definido
    contagem_viaturas_por_unidade = {}
    unidade_filtro = request.args.get('unidade_id')

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            # Pega os dados do formulário
            unidade_id_form = request.form['unidade_id']
            prefixo = request.form['prefixo'].strip() # Usamos .strip() para remover espaços extras
            status = request.form['status']
            hora_entrada = request.form.get('hora_entrada')
            hora_saida = request.form.get('hora_saida')

            # Passo 1: Verificar se o prefixo JÁ EXISTE em qualquer unidade
            cursor.execute("SELECT id FROM viaturas WHERE prefixo = %s", (prefixo,))
            viatura_existente = cursor.fetchone()

            # Passo 2: Se a viatura já existe, mostrar erro e parar
            if viatura_existente:
                flash(f'O prefixo "{prefixo}" já está cadastrado no sistema. Por favor, verifique.', 'danger')
                return redirect(url_for('cadastro_viaturas', unidade_id=unidade_filtro))

            # Passo 3: Se não existe, prosseguir com a inserção
            else:
                cursor.execute("""
                    INSERT INTO viaturas (unidade_id, prefixo, status, hora_entrada, hora_saida)
                    VALUES (%s, %s, %s, %s, %s)
                """, (unidade_id_form, prefixo, status, hora_entrada, hora_saida))
                conn.commit()
                flash('Viatura cadastrada com sucesso!', 'success')
                # Redireciona para a página de cadastro, filtrando pela unidade que acabou de ser cadastrada
                return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id_form))

        # --- Lógica de GET (para carregar a página) ---
        cursor.execute("SELECT id, nome_unidade AS nome FROM unidades") # Corrigido para nome_unidade se aplicável
        unidades = cursor.fetchall()

        if unidade_filtro:
            cursor.execute("""
                SELECT v.id, u.nome_unidade AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
                FROM viaturas v JOIN unidades u ON v.unidade_id = u.id
                WHERE v.unidade_id = %s ORDER BY v.prefixo ASC
            """, (unidade_filtro,))
        else:
            cursor.execute("""
                SELECT v.id, u.nome_unidade AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
                FROM viaturas v JOIN unidades u ON v.unidade_id = u.id
                ORDER BY u.nome_unidade ASC, v.prefixo ASC
            """)
        viaturas = cursor.fetchall()

        cursor.execute("""
            SELECT unidade_id, COUNT(*) as quantidade FROM viaturas GROUP BY unidade_id
        """)
        contagem_viaturas_por_unidade = {row['unidade_id']: row['quantidade'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT c.id, u.nome_unidade AS unidade_nome, c.cfp, c.telefone
            FROM contatos c JOIN unidades u ON c.unidade_id = u.id
        """)
        contatos = cursor.fetchall()

    except MySQLdb.Error as err:
        flash(f"Database error loading page: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()

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
# Lista das colunas que são do tipo TIME no banco
        colunas_de_horario = ['chegada_delegacia', 'entrega_ro', 'saida_delegacia']
        
        # Função auxiliar para formatar a 'duração de tempo' (timedelta) para o formato de hora
        def formatar_timedelta_para_hora(td):
            if pd.isnull(td):
                return '' # Retorna um texto vazio se o dado for nulo
            
            # Converte a duração total em segundos
            segundos_totais = int(td.total_seconds())
            
            # Calcula horas, minutos e segundos a partir do total de segundos
            horas, resto = divmod(segundos_totais, 3600)
            minutos, segundos = divmod(resto, 60)
            
            # Monta o texto no formato HH:MM:SS e adiciona a aspa na frente
            # para forçar o Excel a tratar como texto puro
            return f"'{horas:02}:{minutos:02}:{segundos:02}"

        # Aplica a nossa nova função de formatação em cada coluna de horário
        for coluna in colunas_de_horario:
            if coluna in df.columns:
                df[coluna] = df[coluna].apply(formatar_timedelta_para_hora)

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

# ✏️ Editar viatura (com validação de prefixo duplicado)
@app.route('/editar_viatura/<int:viatura_id>', methods=['GET', 'POST'])
def editar_viatura(viatura_id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            # Pega os dados do formulário de edição
            unidade_id = request.form['unidade_id']
            prefixo = request.form['prefixo'].strip()
            status = request.form['status']
            hora_entrada = request.form.get('hora_entrada')
            hora_saida = request.form.get('hora_saida')

            # VERIFICAÇÃO: Checa se OUTRA viatura (id != viatura_id) já usa este prefixo
            cursor.execute(
                "SELECT id FROM viaturas WHERE prefixo = %s AND id != %s",
                (prefixo, viatura_id)
            )
            outro_com_mesmo_prefixo = cursor.fetchone()

            # Se encontrou outra viatura com o mesmo prefixo, mostra erro
            if outro_com_mesmo_prefixo:
                flash(f'O prefixo "{prefixo}" já está em uso por outra viatura. Por favor, escolha outro.', 'danger')
                # Recarrega a página de edição sem salvar
                return redirect(url_for('editar_viatura', viatura_id=viatura_id))

            # Se o prefixo é único, prossegue com a atualização
            cursor.execute("""
                UPDATE viaturas
                SET unidade_id = %s, prefixo = %s, status = %s, hora_entrada = %s, hora_saida = %s
                WHERE id = %s
            """, (unidade_id, prefixo, status, hora_entrada, hora_saida, viatura_id))
            conn.commit()
            
            flash('Viatura atualizada com sucesso!', 'success')
            return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

        # --- Lógica de GET (para carregar a página de edição pela primeira vez) ---
        cursor.execute("SELECT * FROM viaturas WHERE id = %s", (viatura_id,))
        viatura = cursor.fetchone()

        if not viatura:
            flash('Viatura não encontrada.', 'danger')
            return redirect(url_for('cadastro_viaturas'))

        cursor.execute("SELECT id, nome_unidade FROM unidades ORDER BY nome_unidade")
        unidades = cursor.fetchall()
        
        return render_template('editar_viatura.html', viatura=viatura, unidades=unidades)

    except MySQLdb.Error as err:
        flash(f"Database error on edit page: {err}", 'danger')
        return redirect(url_for('cadastro_viaturas'))
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
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            # Pega todos os dados do formulário
            delegacia = request.form.get('delegacia', '').strip()
            viatura_prefixo = request.form.get('viatura_prefixo', '').strip()
            fato = request.form.get('fato', '').strip()
            status = request.form.get('status', '').strip()
            protocolo = request.form.get('protocolo', '').strip()
            ro_cadg = request.form.get('ro_cadg', '').strip()
            chegada = request.form.get('chegada', '').strip()
            entrega_ro = request.form.get('entrega_ro', '').strip()
            saida = request.form.get('saida', '').strip()

            # Lógica de Fuso Horário para MS (UTC-4)
            fuso_horario_ms = pytz.timezone('America/Campo_Grande')
            data_do_registro = datetime.now(fuso_horario_ms)
            
            # Cálculo de Tempo Condicional
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
                    flash('Um dos horários fornecidos tem formato inválido. Utilize HH:MM.', 'danger')
                    return redirect(url_for('gerenciar_ocorrencias'))

            # Comando INSERT final e correto com 12 colunas e 12 valores
            cursor.execute("""
                INSERT INTO ocorrencias_cepol
                (delegacia, viatura_prefixo, fato, status, protocolo, ro_cadg, 
                 chegada_delegacia, entrega_ro, saida_delegacia, 
                 tempo_total_dp, tempo_entrega_dp, data_registro)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, 
            (delegacia or None, viatura_prefixo or None, fato or None, status or None, 
             protocolo or None, ro_cadg or None, chegada or None, entrega_ro or None, 
             saida or None, tempo_total_dp, tempo_entrega_dp, data_do_registro))

            conn.commit()
            flash('Ocorrência registrada com sucesso!', 'success')
            return redirect(url_for('gerenciar_ocorrencias'))

        # Lógica de GET para carregar a página
        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY data_registro DESC")
        ocorrencias = cursor.fetchall()

    except MySQLdb.Error as err:
        flash(f"Erro no banco de dados ao gerenciar ocorrências: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()

    return render_template('ocorrencias_cepol.html', ocorrencias=ocorrencias)

# 📂 Rota para ARQUIVAR ocorrência (substitui a antiga 'excluir_ocorrencia')
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
        flash(f'Erro ao arquivar ocorrência: {err}', 'danger')
    except Exception as e:
        flash(f'Ocorreu um erro inesperado ao arquivar: {e}', 'danger')
    finally:
        if cursor:
            cursor.close()

    return redirect(url_for('gerenciar_ocorrencias'))

# ✏️ Rota para editar ocorrência (com campo de viatura)
# ✏️ Rota para editar ocorrência (com campo de delegacia)
@app.route('/editar_ocorrencia/<int:id>', methods=['GET', 'POST'])
def editar_ocorrencia(id):
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        if request.method == 'POST':
            # Pega todos os dados do formulário, incluindo o novo campo
            delegacia = request.form.get('delegacia', '').strip() # <-- NOVO
            fato = request.form.get('fato', '').strip()
            status = request.form.get('status', '').strip()
            protocolo = request.form.get('protocolo', '').strip()
            viatura_prefixo = request.form.get('viatura_prefixo', '').strip()
            ro_cadg = request.form.get('ro_cadg', '').strip()
            chegada = request.form.get('chegada', '').strip()
            entrega_ro = request.form.get('entrega_ro', '').strip()
            saida = request.form.get('saida', '').strip()

            # A validação de campos obrigatórios foi removida, mas pode ser adicionada aqui se necessário
            
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

            # ATUALIZADO: Adiciona 'delegacia' ao comando UPDATE
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

        # --- Lógica de GET (carrega os dados da ocorrência para exibir no formulário) ---
        cursor.execute("SELECT * FROM ocorrencias_cepol WHERE id = %s", (id,))
        ocorrencia = cursor.fetchone()

        if not ocorrencia:
            flash('Ocorrência não encontrada.', 'danger')
            return redirect(url_for('gerenciar_ocorrencias'))

        # Formatação de campos de tempo para exibição
        ocorrencia['chegada_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('chegada_delegacia'))
        ocorrencia['entrega_ro'] = ensure_hh_mm_format_for_display(ocorrencia.get('entrega_ro'))
        ocorrencia['saida_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('saida_delegacia'))

    except MySQLdb.Error as err:
        flash(f"Erro no banco de dados ao carregar/atualizar: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()

    return render_template('editar_ocorrencia.html', ocorrencia=ocorrencia)

    # 🗑️ Rota para EXCLUIR PERMANENTEMENTE uma única ocorrência
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
        flash(f'Erro ao excluir ocorrência: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()
    return redirect(url_for('gerenciar_ocorrencias'))

    # 📦 Rota para ARQUIVAR e LIMPAR TODAS AS OCORRÊNCIAS
@app.route('/limpar_todas_ocorrencias', methods=['POST'])
def limpar_todas_ocorrencias():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Inicia uma transação: se algo der errado, nada é feito.
        conn.begin()
        
        # 1. Copia todos os dados da tabela principal para a tabela de histórico
        cursor.execute("INSERT INTO historico_ocorrencias SELECT * FROM ocorrencias_cepol")
        
        # 2. Apaga todos os dados da tabela principal
        cursor.execute("DELETE FROM ocorrencias_cepol")
        
        # 3. Confirma as duas operações
        conn.commit()
        
        flash('Todas as ocorrências foram arquivadas e a tela foi limpa com sucesso!', 'success')

    except MySQLdb.Error as err:
        if conn:
            conn.rollback() # Desfaz a operação em caso de erro
        flash(f'Erro no banco de dados ao arquivar e limpar: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()

    return redirect(url_for('gerenciar_ocorrencias'))

    # 📄 Rota para fazer o BACKUP de todas as ocorrências para Excel ANTES de limpar
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
            flash('Não há ocorrências para fazer backup.', 'info')
            return redirect(url_for('gerenciar_ocorrencias'))

        df = pd.DataFrame(ocorrencias)
        output = BytesIO() # Cria um arquivo em memória

        # Gera o nome do arquivo com a data e hora atual
        nome_arquivo = f"backup_ocorrencias_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.xlsx"

        df.to_excel(output, index=False, sheet_name='Backup_Ocorrencias')
        output.seek(0)
        
        # Envia o arquivo em memória para o navegador do usuário fazer o download
        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=nome_arquivo)

    except Exception as e:
        flash(f"Ocorreu um erro ao gerar o backup em Excel: {e}", 'danger')
        return redirect(url_for('gerenciar_ocorrencias'))
    finally:
        if cursor:
            cursor.close()

            # 🏛️ Rota para VISUALIZAR o histórico de ocorrências arquivadas
@app.route('/historico')
def historico():
    conn = None
    cursor = None
    historico_ocorrencias = []
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        # Busca os dados da tabela de histórico, não da tabela principal
        cursor.execute("SELECT * FROM historico_ocorrencias ORDER BY id DESC")
        historico_ocorrencias = cursor.fetchall()
    except MySQLdb.Error as err:
        flash(f"Erro ao carregar o histórico: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
            
    # Renderiza um NOVO template chamado historico.html
    return render_template('historico.html', ocorrencias=historico_ocorrencias)

    # 📜 Rota para exportar o HISTÓRICO COMPLETO para Excel
# 📜 Rota para exportar o HISTÓRICO COMPLETO para Excel
# 📜 Rota para exportar o HISTÓRICO COMPLETO para Excel (com formatação de hora)
@app.route('/exportar_historico_excel')
def exportar_historico_excel():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        # Seleciona da tabela de HISTÓRICO
        cursor.execute("SELECT * FROM historico_ocorrencias ORDER BY id ASC")
        ocorrencias = cursor.fetchall()

        if not ocorrencias:
            flash('Não há dados no histórico para exportar.', 'info')
            return redirect(url_for('historico'))

        df = pd.DataFrame(ocorrencias)
        
        # --- INÍCIO DO BLOCO DE CORREÇÃO DE HORÁRIO ---
        colunas_de_horario = ['chegada_delegacia', 'entrega_ro', 'saida_delegacia']
        
        def formatar_timedelta_para_hora(td):
            if pd.isnull(td):
                return ''
            segundos_totais = int(td.total_seconds())
            horas, resto = divmod(segundos_totais, 3600)
            minutos, segundos = divmod(resto, 60)
            return f"'{horas:02}:{minutos:02}:{segundos:02}"

        for coluna in colunas_de_horario:
            if coluna in df.columns:
                df[coluna] = df[coluna].apply(formatar_timedelta_para_hora)
        # --- FIM DO BLOCO DE CORREÇÃO ---

        output = BytesIO()
        nome_arquivo = f"historico_completo_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
        # Usando 'xlsxwriter' pode dar um resultado melhor no Excel
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='Historico_Completo')
        writer.close() # Alterado de save() para close() que é mais comum
        
        output.seek(0)

        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=nome_arquivo)

    except Exception as e:
        flash(f"Ocorreu um erro ao gerar o Excel do histórico: {e}", 'danger')
        return redirect(url_for('historico'))
    finally:
        if cursor:
            cursor.close()

            # 🔥 Rota para ZERAR PERMANENTEMENTE o histórico (usar após o backup)
@app.route('/zerar_historico_confirmado', methods=['POST'])
def zerar_historico_confirmado():
    conn = None
    cursor = None
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Apaga TODOS os registros da tabela de histórico
        cursor.execute("DELETE FROM historico_ocorrencias")
        
        conn.commit()
        flash('O histórico de ocorrências foi zerado com sucesso!', 'warning')

    except MySQLdb.Error as err:
        if conn:
            conn.rollback() 
        flash(f'Erro no banco de dados ao zerar o histórico: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()

    return redirect(url_for('historico'))

# --- Rota para Relatórios ---
@app.route('/relatorios')
def relatorios():
    conn = None
    cursor = None
    # Define valores padrão para todas as variáveis no início.
    supervisores_string = "Nenhum supervisor cadastrado."
    cfps_data = []
    viaturas_data = []
    viaturas_por_unidade = []
    viaturas_por_status = []
    totais_viaturas = {
        'total_viaturas_geral': 0, 'total_capital': 0, 'total_interior': 0, 
        'total_motos': 0, 'soma_atendimento_copom': 0, 'total_capital_interior_motos': 0
    }

    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)

        # --- Seção 1 a 5: Buscando dados gerais (Supervisores, Contatos, etc.) ---
        # (O código para buscar supervisores, contatos, viaturas, etc., continua aqui igual ao seu original)
        cursor.execute("SELECT supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento FROM supervisores WHERE id = 1")
        supervisores_db_row = cursor.fetchone()
        if supervisores_db_row:
            supervisores_parts = [f"<strong>{k.replace('_', ' ').title()}:</strong> {v}" for k, v in supervisores_db_row.items() if v]
            if supervisores_parts:
                supervisores_string = " - ".join(supervisores_parts)

        cursor.execute("SELECT c.id, u.nome_unidade AS unidade_nome, c.cfp, c.telefone FROM contatos c JOIN unidades u ON c.unidade_id = u.id ORDER BY u.nome_unidade, c.cfp")
        cfps_data = cursor.fetchall()

        cursor.execute("SELECT v.*, u.nome_unidade AS unidade_nome FROM viaturas v JOIN unidades u ON v.unidade_id = u.id ORDER BY u.nome_unidade, v.prefixo")
        viaturas_data = cursor.fetchall()

        cursor.execute("SELECT u.nome_unidade AS unidade_nome, COUNT(v.id) AS quantidade FROM viaturas v JOIN unidades u ON v.unidade_id = u.id GROUP BY u.nome_unidade ORDER BY u.nome_unidade")
        viaturas_por_unidade = cursor.fetchall()

        cursor.execute("SELECT status, COUNT(id) AS quantidade FROM viaturas GROUP BY status ORDER BY status")
        viaturas_por_status = cursor.fetchall()

        # --- Seção 6: Cálculo de Totais de Viaturas (LÓGICA CORRETA COM PANDAS) ---
        cursor.execute("SELECT status FROM viaturas")
        lista_status_raw = cursor.fetchall()

        if lista_status_raw:
            df = pd.DataFrame(lista_status_raw)
            df['status'] = df['status'].fillna('').str.strip()

            total_interior = (df['status'] == 'INTERIOR').sum()
            total_motos = (df['status'] == 'MOTO').sum()
            # Define a lista explícita de status que devem ser somados em 'Capital'
            status_capital = [
                'ADM', 'CFP', 'FORÇATÁTICA', 'RP', 'TRÂNSITO', 'ADJ CFP', 
                'ROTAC', 'CANIL', 'BOPE', 'ESCOLAR/PROMUSE', 'POL.COMUNITÁRIO', 
                # 'JUIZADO',  <-- Removido da soma de Capital
                'TRANSITO/BLITZ'
            ]
# Soma apenas as viaturas cujo status está na lista acima
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
            # Adicionando um print para os logs do Render, para termos certeza
            print(f"DEBUG: Totais calculados: {totais_viaturas}")
            
    except MySQLdb.Error as err:
        flash(f"Erro no banco de dados ao carregar relatórios: {err}", 'danger')
        
    finally:
        if cursor:
            cursor.close()

    return render_template('relatorios.html',
                           supervisores_string=supervisores_string,
                           cfps=cfps_data,
                           viaturas=viaturas_data,
                           viaturas_por_unidade=viaturas_por_unidade,
                           viaturas_por_status=viaturas_por_status,
                           totais_viaturas=totais_viaturas)

@app.route('/debug-status')
def debug_status():
    conn = None
    cursor = None
    output_html = "<h1>Diagnóstico de Status de Viaturas</h1>"
    
    try:
        conn = get_db()
        cursor = conn.cursor(MySQLdb.cursors.DictCursor)
        
        cursor.execute("SELECT DISTINCT status FROM viaturas")
        unique_statuses = cursor.fetchall()
        
        if not unique_statuses:
            return "Nenhum status encontrado na tabela de viaturas."

        output_html += "<table border='1' cellpadding='5'><tr><th>Status do Banco</th><th>É 'INTERIOR'?</th><th>É 'MOTO'?</th></tr>"

        for row in unique_statuses:
            status_original = row['status']
            
            # Aplica a mesma limpeza que usamos no código de relatórios
            status_limpo = status_original.strip() if status_original else ''
            
            # Realiza as comparações exatas
            is_interior = (status_limpo == 'INTERIOR')
            is_moto = (status_limpo == 'MOTO')
            
            # Monta a linha da tabela de diagnóstico
            output_html += f"<tr><td>'{status_limpo}'</td><td>{is_interior}</td><td>{is_moto}</td></tr>"

        output_html += "</table>"
        return output_html

    except Exception as e:
        return f"Ocorreu um erro durante o diagnóstico: {e}"
    finally:
        if cursor:
            cursor.close()


# ... (restante do seu app.py, incluindo app.run(debug=True)

# ESTE BLOCO DEVE ESTAR NO FINAL DO SEU ARQUIVO
if __name__ == '__main__':
    app.run(debug=True)