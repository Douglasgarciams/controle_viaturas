import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from datetime import datetime, timedelta, time
import psycopg2
import psycopg2.extras
import pandas as pd # Certifique-se de que pandas está importado

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'co8bb9fffef7fe3f5892cfd83a5c36d71712e201c128be08b47c90f5589408ed82')

# 🔗 Conexão com PostgreSQL
def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get('DB_HOST'),
        user=os.environ.get('DB_USER'),
        password=os.environ.get('DB_PASSWORD'),
        database=os.environ.get('DB_NAME'),
        port=os.environ.get('DB_PORT', '5432')
    )

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
    return None

# Função para garantir que o valor do tempo esteja em HH:MM para exibição
def ensure_hh_mm_format_for_display(time_value):
    if isinstance(time_value, time):
        return time_value.strftime("%H:%M")

    if isinstance(time_value, str) and len(time_value) == 5 and ':' in time_value:
        try:
            datetime.strptime(time_value, "%H:%M")
            return time_value
        except ValueError:
            pass

    minutes = parse_minutes_from_string(time_value)
    if minutes is not None:
        return format_minutes_to_hh_mm(minutes)

    return ''

# 🔧 Status disponíveis
STATUS_OPTIONS = [
    'ADM', 'CFP', 'FORÇA TATICA', 'RP', 'TRANSITO', 'ADJ CFP', 'INTERIOR',
    'MOTO', 'ROTAC', 'CANIL', 'BOPE', 'ESCOLAR/PROMUSE', 'POL.COMUNITARIO',
    'JUIZADO', 'TRANSITO/BLITZ'
]

# --- FUNÇÕES PARA GARANTIR QUE AS TABELAS EXISTAM ---

def ensure_supervisores_table_and_initial_entry():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS supervisores (
                id SERIAL PRIMARY KEY,
                supervisor_operacoes VARCHAR(100) DEFAULT '',
                coordenador VARCHAR(100) DEFAULT '',
                supervisor_despacho VARCHAR(100) DEFAULT '',
                supervisor_atendimento VARCHAR(100) DEFAULT '',
                last_updated TIMESTAMP WITH TIME ZONE
            )
        """)
        conn.commit()
        cursor.execute("SELECT COUNT(*) FROM supervisores")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO supervisores (supervisor_operacoes, coordenador, supervisor_despacho, supervisor_atendimento, last_updated)
                VALUES (%s, %s, %s, %s, NOW())
            """, ('', '', '', ''))
            conn.commit()
            print("Entrada inicial para a tabela 'supervisores' criada com sucesso.")
        else:
            print("Tabela 'supervisores' já existe e possui entradas.")
    except psycopg2.Error as err:
        print(f"Erro ao inicializar a tabela 'supervisores': {err}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

# MODIFICADO: Função para garantir que a tabela 'unidades' exista e inserir as 9 unidades corretas
def ensure_unidades_table_and_initial_entries():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unidades (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(100) NOT NULL UNIQUE
            )
        """)
        conn.commit()
        print("Tabela 'unidades' verificada/criada.")

        # Inserir unidades iniciais se a tabela estiver vazia
        cursor.execute("SELECT COUNT(*) FROM unidades")
        if cursor.fetchone()[0] == 0:
            # ESTA É A LISTA ATUALIZADA DAS 9 UNIDADES:
            unidades_iniciais = [
                ('1º BPM',),
                ('9º BPM',),
                ('10º BPM',),
                ('5ª CIPM',),
                ('6ª CIPM',),
                ('10ª CIPM',),
                ('11ª CIPM',),
                ('BPTRAN',),
                ('BPCHOQUE',)
            ]
            cursor.executemany("INSERT INTO unidades (nome) VALUES (%s)", unidades_iniciais)
            conn.commit()
            print("Unidades iniciais inseridas com sucesso.")
        else:
            print("Tabela 'unidades' já possui entradas.")

    except psycopg2.Error as err:
        print(f"Erro ao inicializar a tabela 'unidades': {err}")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn and not conn.closed: conn.close()


def ensure_viaturas_table():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS viaturas (
                id SERIAL PRIMARY KEY,
                unidade_id INT NOT NULL,
                prefixo VARCHAR(50) NOT NULL,
                status VARCHAR(50) NOT NULL,
                hora_entrada VARCHAR(5) DEFAULT NULL,
                hora_saida VARCHAR(5) DEFAULT NULL,
                FOREIGN KEY (unidade_id) REFERENCES unidades(id)
            )
        """)
        conn.commit()
        print("Tabela 'viaturas' verificada/criada.")
    except psycopg2.Error as err:
        print(f"Erro ao inicializar a tabela 'viaturas': {err}")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn and not conn.closed: conn.close()

def ensure_contatos_table():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contatos (
                id SERIAL PRIMARY KEY,
                unidade_id INT NOT NULL,
                cfp VARCHAR(100) NOT NULL,
                telefone VARCHAR(20) DEFAULT NULL,
                FOREIGN KEY (unidade_id) REFERENCES unidades(id)
            )
        """)
        conn.commit()
        print("Tabela 'contatos' verificada/criada.")
    except psycopg2.Error as err:
        print(f"Erro ao inicializar a tabela 'contatos': {err}")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn and not conn.closed: conn.close()

def ensure_ocorrencias_cepol_table():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ocorrencias_cepol (
                id SERIAL PRIMARY KEY,
                fato VARCHAR(255) NOT NULL,
                status VARCHAR(50) NOT NULL,
                protocolo VARCHAR(100) NOT NULL,
                ro_cadg VARCHAR(100) NOT NULL,
                chegada_delegacia VARCHAR(5) NOT NULL,
                entrega_ro VARCHAR(5) NOT NULL,
                saida_delegacia VARCHAR(5) NOT NULL,
                tempo_total_dp VARCHAR(10),
                tempo_entrega_dp VARCHAR(10),
                data_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        print("Tabela 'ocorrencias_cepol' verificada/criada.")
    except psycopg2.Error as err:
        print(f"Erro ao inicializar a tabela 'ocorrencias_cepol': {err}")
        if conn: conn.rollback()
    finally:
        if cursor: cursor.close()
        if conn and not conn.closed: conn.close()

# --- CHAMADAS DAS FUNÇÕES DE CRIAÇÃO DE TABELA ---
ensure_supervisores_table_and_initial_entry()
ensure_unidades_table_and_initial_entries() # <-- ESTA FUNÇÃO FOI ATUALIZADA
ensure_viaturas_table()
ensure_contatos_table()
ensure_ocorrencias_cepol_table()


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
    contatos = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

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

        elif request.method == 'POST' and request.form.get('tipo') == 'contato':
            unidade_id = request.form.get('unidade')
            nome_cfp = request.form.get('nome')
            telefone = request.form.get('telefone')

            cursor.execute("SELECT * FROM contatos WHERE unidade_id=%s", (unidade_id,))
            if cursor.fetchone():
                cursor.execute(
                    "UPDATE contatos SET cfp=%s, telefone=%s WHERE unidade_id=%s",
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

        cursor.execute("SELECT * FROM supervisores WHERE id = 1")
        row_supervisores = cursor.fetchone()
        if row_supervisores:
            supervisores_data = row_supervisores

        cursor.execute("SELECT id, nome FROM unidades ORDER BY nome ASC") # Adicionado ORDER BY
        unidades = cursor.fetchall()

        cursor.execute("""
                                SELECT v.id, v.prefixo, v.unidade_id, v.status, u.nome AS unidade_nome
                                FROM viaturas v JOIN unidades u ON v.unidade_id = u.id
                                ORDER BY u.nome, v.prefixo
                                """)
        viaturas_data = cursor.fetchall()
        viaturas = viaturas_data

        cursor.execute("""
            SELECT c.*, u.nome AS unidade_nome
            FROM contatos c JOIN unidades u ON c.unidade_id = u.id
        """)
        contatos = cursor.fetchall()

    except psycopg2.Error as err:
        flash(f"Database error: {err}", 'danger')
        unidades = []
        viaturas = []
        contatos = []
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return render_template('index.html', unidades=unidades, status_options=STATUS_OPTIONS,
                           viaturas=viaturas, contatos=contatos, supervisores=supervisores_data)

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
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

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

        cursor.execute("SELECT id, nome FROM unidades ORDER BY nome ASC") # Adicionado ORDER BY
        unidades = cursor.fetchall()

        if unidade_filtro:
            cursor.execute("""
                SELECT v.id, u.nome AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
                FROM viaturas v
                JOIN unidades u ON v.unidade_id = u.id
                WHERE v.unidade_id = %s
            """, (unidade_filtro,))
        else:
            cursor.execute("""
                SELECT v.id, u.nome AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
                FROM viaturas v
                JOIN unidades u ON v.unidade_id = u.id
                ORDER BY u.nome ASC, v.prefixo ASC
            """)
        viaturas = cursor.fetchall()

        cursor.execute("""
            SELECT unidade_id, COUNT(*) as quantidade
            FROM viaturas
            GROUP BY unidade_id
        """)
        contagem_viaturas_por_unidade = {row['unidade_id']: row['quantidade'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT c.id, u.nome AS unidade_nome, c.cfp, c.telefone
            FROM contatos c
            JOIN unidades u ON c.unidade_id = u.id
        """)
        contatos = cursor.fetchall()

    except psycopg2.Error as err:
        flash(f"Database error loading vehicles: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

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
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute("SELECT * FROM ocorrencias_cepol ORDER BY data_registro DESC")
        ocorrencias = cursor.fetchall()

        if not ocorrencias:
            flash('Não há dados para exportar para Excel.', 'info')
            return redirect(url_for('gerenciar_ocorrencias'))

        # --- A CORREÇÃO ESTÁ AQUI: CONVERTER PARA DATAFRAME ---
        # Convert list of dict-like rows to a list of dicts, then to DataFrame
        ocorrencias_dicts = [dict(row) for row in ocorrencias]
        df = pd.DataFrame(ocorrencias_dicts)
        # --- FIM DA CORREÇÃO ---

        from io import BytesIO
        output = BytesIO()
        writer = pd.ExcelWriter(output, engine='openpyxl')
        df.to_excel(writer, index=False, sheet_name='Ocorrencias')
        writer.close()
        output.seek(0)

        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name='relatorio_ocorrencias_cepol.xlsx')

    except psycopg2.Error as err:
        flash(f"Erro no banco de dados ao exportar: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado ao exportar: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return redirect(url_for('gerenciar_ocorrencias'))

@app.route('/editar_contato/<int:contato_id>', methods=['GET'])
def editar_contato(contato_id):
    conn = None
    cursor = None
    contato = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("SELECT * FROM contatos WHERE id = %s", (contato_id,))
        contato = cursor.fetchone()
    except psycopg2.Error as err:
        flash(f"Database error: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    if contato is None:
        flash('Contato não encontrado.', 'danger')
        return redirect(url_for('cadastro_viaturas'))

    return render_template('editar_contato.html', contato=contato)

@app.route('/editar_contato/<int:contato_id>', methods=['POST'])
def editar_contato_post(contato_id):
    conn = None
    cursor = None
    unidade_id = request.form['unidade_id']
    try:
        unidade_id = request.form['unidade_id']
        cfp = request.form['cfp']
        telefone = request.form['telefone']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE contatos
            SET unidade_id = %s, cfp = %s, telefone = %s
            WHERE id = %s
        """, (unidade_id, cfp, telefone, contato_id))

        conn.commit()
        flash('Contato atualizado com sucesso!', 'success')
    except psycopg2.Error as err:
        flash(f"Database error updating contact: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/adicionar_contato', methods=['POST'])
def adicionar_contato():
    conn = None
    cursor = None
    unidade_id = request.form.get('unidade_id', '')

    try:
        unidade_id = request.form['unidade_id']
        cfp = request.form['cfp']
        telefone = request.form['telefone']

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO contatos (unidade_id, cfp, telefone)
            VALUES (%s, %s, %s)
        """, (unidade_id, cfp, telefone))

        conn.commit()
        flash('Contato cadastrado com sucesso!', 'success')
    except psycopg2.Error as err:
        flash(f"Database error adding contact: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/excluir_contato/<int:contato_id>', methods=['POST'])
def excluir_contato(contato_id):
    conn = None
    cursor = None
    unidade_id = ''

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute("SELECT unidade_id FROM contatos WHERE id = %s", (contato_id,))
        contato = cursor.fetchone()
        unidade_id = contato['unidade_id'] if contato else ''

        cursor.execute("DELETE FROM contatos WHERE id = %s", (contato_id,))
        conn.commit()
        flash('Contato excluído com sucesso!', 'success')
    except psycopg2.Error as err:
        flash(f'Database error deleting contact: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/excluir_viatura/<int:viatura_id>', methods=['POST'])
def excluir_viatura(viatura_id):
    conn = None
    cursor = None
    unidade_id = ''

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute("SELECT unidade_id FROM viaturas WHERE id = %s", (viatura_id,))
        viatura = cursor.fetchone()

        if not viatura:
            flash('Viatura não encontrada.', 'danger')
            return redirect(url_for('cadastro_viaturas'))

        unidade_id = viatura['unidade_id']

        cursor.execute("DELETE FROM viaturas WHERE id = %s", (viatura_id,))
        conn.commit()
        flash('Viatura excluída com sucesso!', 'success')
    except psycopg2.Error as err:
        flash(f'Database error deleting vehicle: {err}', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return redirect(url_for('cadastro_viaturas', unidade_id=unidade_id))

@app.route('/editar_viatura/<int:viatura_id>', methods=['GET', 'POST'])
def editar_viatura(viatura_id):
    conn = None
    cursor = None
    viatura = None
    unidades = []
    unidade_id_for_redirect = ''

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

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
            SELECT v.id, v.unidade_id, u.nome AS unidade_nome, v.prefixo, v.status, v.hora_entrada, v.hora_saida
            FROM viaturas v
            JOIN unidades u ON v.unidade_id = u.id
            WHERE v.id = %s
        """, (viatura_id,))
        viatura = cursor.fetchone()

        cursor.execute("SELECT id, nome FROM unidades ORDER BY nome ASC") # Adicionado ORDER BY
        unidades = cursor.fetchall()

    except psycopg2.Error as err:
        flash(f"Database error editing vehicle: {err}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    if viatura:
        return render_template('editar_viatura.html', viatura=viatura, unidades=unidades)
    else:
        flash('Viatura não encontrada.', 'danger')
        return redirect(url_for('cadastro_viaturas'))


# --- ROTAS PARA OCORRÊNCIAS CEPOL ---
@app.route('/ocorrencias', methods=['GET', 'POST'])
def gerenciar_ocorrencias():
    conn = None
    cursor = None
    ocorrencias = []

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

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

    except psycopg2.Error as err:
        flash(f"Erro no banco de dados ao gerenciar ocorrências: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return render_template('ocorrencias_cepol.html', ocorrencias=ocorrencias)


@app.route('/excluir_ocorrencia/<int:id>', methods=['POST'])
def excluir_ocorrencia(id):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ocorrencias_cepol WHERE id = %s", (id,))
        conn.commit()
        flash('Ocorrência excluída com sucesso!', 'success')
    except psycopg2.Error as err:
        flash(f'Erro ao excluir ocorrência: {err}', 'danger')
    except Exception as e:
        flash(f'Ocorreu um erro inesperado ao excluir: {e}', 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()
    return redirect(url_for('gerenciar_ocorrencias'))

@app.route('/editar_ocorrencia/<int:id>', methods=['GET', 'POST'])
def editar_ocorrencia(id):
    conn = None
    cursor = None
    ocorrencia = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

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

        cursor.execute("SELECT * FROM ocorrencias_cepol WHERE id = %s", (id,))
        ocorrencia = cursor.fetchone()

        if not ocorrencia:
            flash('Ocorrência não encontrada.', 'danger')
            return redirect(url_for('gerenciar_ocorrencias'))

        ocorrencia['chegada_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('chegada_delegacia'))
        ocorrencia['entrega_ro'] = ensure_hh_mm_format_for_display(ocorrencia.get('entrega_ro'))
        ocorrencia['saida_delegacia'] = ensure_hh_mm_format_for_display(ocorrencia.get('saida_delegacia'))

    except psycopg2.Error as err:
        flash(f"Erro no banco de dados ao carregar/atualizar: {err}", 'danger')
    except Exception as e:
        flash(f"Ocorreu um erro inesperado: {e}", 'danger')
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

    return render_template('editar_ocorrencia.html', ocorrencia=ocorrencia)

import psycopg2
import psycopg2.extras
import json # Adicione esta importação para json.dumps

# Supondo que 'get_db_connection' e 'app' já estão definidos em seu app.py
# Exemplo básico, ajuste conforme sua configuração real
from flask import Flask, render_template, request, redirect, url_for, flash # Removi jsonify pois não estava sendo usado no seu trecho

# APENAS PARA EXEMPLIFICAR A ROTA DE RELATÓRIOS.
# VOCÊ DEVE TER SEU 'app' e 'get_db_connection' DEFINIDOS ANTES.
# Se já tiver isso, IGNORE essas linhas de exemplo.
# --- EXEMPO DE COMO PODERIAM SER DEFINIDOS (NÃO COPIE SE JÁ TIVER) ---
# app = Flask(__name__)
# app.secret_key = 'sua_chave_secreta_muito_secreta' # Substitua por uma chave segura
# DATABASE_URL = "postgres://user:pass@host:port/dbname" # Substitua pela sua URL de conexão REAL
# def get_db_connection():
#     return psycopg2.connect(DATABASE_URL)
# --- FIM DO EXEMPLO ---


@app.route('/relatorios')
def relatorios():
    conn = None
    cursor = None

    supervisores_string = ""
    # As variáveis abaixo foram declaradas no SEU código.
    # Elas serão passadas para o template, mesmo que estejam vazias.
    cfps_data = []
    viaturas_data = []
    viaturas_por_unidade = []
    viaturas_por_status = []
    totais_viaturas = {} # Esta variável estava no SEU código inicial, então ela será passada.

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Consulta para supervisores (esta parte era do SEU código)
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
                pass # Seu pass original

        # --- AQUI É ONDE SEU CÓDIGO ORIGINAL CONTINUARIA COM AS OUTRAS CONSULTAS ---
        # Exemplo (VOCÊ PRECISA TER ESSAS CONSULTAS NO SEU CÓDIGO real, caso contrário elas ficarão vazias):

        # PARA cfps_data (usado como 'cfps' no HTML)
        cursor.execute("""
            SELECT u.nome AS unidade_nome, c.cfp_nome, c.telefone
            FROM contatos c
            JOIN unidades u ON c.unidade_id = u.id
            ORDER BY u.nome, c.cfp_nome
        """)
        cfps_data = cursor.fetchall()

        # PARA viaturas_data (usado como 'viaturas' no HTML)
        cursor.execute("""
            SELECT v.prefixo, v.status, u.nome AS unidade_nome,
                   TO_CHAR(v.hora_entrada, 'HH24:MI') AS hora_entrada,
                   TO_CHAR(v.hora_saida, 'HH24:MI') AS hora_saida,
                   v.tempo_patrulha
            FROM viaturas v
            JOIN unidades u ON v.unidade_id = u.id
            ORDER BY u.nome, v.prefixo
        """)
        viaturas_data = cursor.fetchall()

        # PARA viaturas_por_unidade (usado como 'viaturas_por_unidade' no HTML)
        cursor.execute("""
            SELECT u.nome AS unidade_nome, COUNT(v.id) AS quantidade
            FROM viaturas v
            JOIN unidades u ON v.unidade_id = u.id
            GROUP BY u.nome
            ORDER BY u.nome
        """)
        viaturas_por_unidade = cursor.fetchall()

        # PARA viaturas_por_status (usado como 'viaturas_por_status' no HTML para JS)
        cursor.execute("""
            SELECT status, COUNT(id) AS quantidade
            FROM viaturas
            GROUP BY status
            ORDER BY status
        """)
        viaturas_por_status = cursor.fetchall() # Isso será json.dumps() abaixo

        # PARA totais_viaturas (se você tinha uma consulta para isso, adicione-a aqui)
        # Se essa variável apenas era declarada vazia no seu código original e não tinha uma consulta
        # para preenchê-la, ela continuará vazia, mas será passada.
        # Se você tinha uma consulta para 'totais_viaturas' que não me passou, insira-a aqui.
        # Exemplo hipotético se você tivesse uma consulta para totais_viaturas:
        cursor.execute("""
            SELECT
                COUNT(CASE WHEN status IN ('CFP', 'ESCOLAR/PROMUSE', 'FORÇATÁTICA', 'JUIZADO', 'ROTAC', 'RP', 'TRÂNSITO', 'CANIL') THEN id END) AS capital_cfp_adjcfp,
                COUNT(CASE WHEN status = 'INTERIOR' THEN id END) AS interior,
                COUNT(CASE WHEN status = 'MOTO' THEN id END) AS moto,
                COUNT(id) AS total_geral,
                COUNT(CASE WHEN status IN ('FORÇATÁTICA', 'RP', 'TRÂNSITO') THEN id END) AS soma_atendimento_copom,
                COUNT(CASE WHEN status NOT IN ('RECOLHIDA', 'MANUTENÇÃO') THEN id END) AS total_ativos,
                COUNT(CASE WHEN status IN ('RECOLHIDA', 'MANUTENÇÃO') THEN id END) AS total_inativos
            FROM viaturas
        """)
        totais_db_row = cursor.fetchone()
        if totais_db_row:
            totais_viaturas = {
                'capital_cfp_adjcfp': totais_db_row['capital_cfp_adjcfp'] or 0,
                'interior': totais_db_row['interior'] or 0,
                'moto': totais_db_row['moto'] or 0,
                'total_geral': totais_db_row['total_geral'] or 0,
                'soma_atendimento_copom': totais_db_row['soma_atendimento_copom'] or 0,
                'total_ativos': totais_db_row['total_ativos'] or 0,
                'total_inativos': totais_db_row['total_inativos'] or 0,
            }
        else:
            totais_viaturas = {
                'capital_cfp_adjcfp': 0, 'interior': 0, 'moto': 0,
                'total_geral': 0, 'soma_atendimento_copom': 0,
                'total_ativos': 0, 'total_inativos': 0,
            }
        # Fim da seção de consulta para totais_viaturas

        # --- A ÚNICA E ESSENCIAL MUDANÇA PARA RENDERIZAR A PÁGINA ---
        return render_template('relatorios.html',
                               supervisores_string=supervisores_string,
                               cfps=cfps_data,
                               viaturas=viaturas_data,
                               viaturas_por_unidade=viaturas_por_unidade,
                               # Converte para JSON para o JavaScript no frontend
                               viaturas_por_status=json.dumps([dict(row) for row in viaturas_por_status]),
                               totais_viaturas=totais_viaturas,
                               # unit_color_map não estava no seu código, não será passado.
                               # Se seu HTML precisar, ele terá que lidar com sua ausência ou você terá que adicioná-lo.
                               )

    except psycopg2.Error as err:
        flash(f"Erro no banco de dados ao gerar relatórios: {err}", 'danger')
        print(f"Erro no DB: {err}") # Ajuda a depurar
        # Retorna o template mesmo com erro, mas com dados vazios
        return render_template('relatorios.html',
                               supervisores_string="", cfps=[], viaturas=[],
                               viaturas_por_unidade=[], viaturas_por_status="[]",
                               totais_viaturas={}, unit_color_map={}) # Adicionei unit_color_map vazio aqui para consistência
    except Exception as e:
        flash(f"Ocorreu um erro inesperado ao gerar relatórios: {e}", 'danger')
        print(f"Erro geral: {e}") # Ajuda a depurar
        # Retorna o template mesmo com erro, mas com dados vazios
        return render_template('relatorios.html',
                               supervisores_string="", cfps=[], viaturas=[],
                               viaturas_por_unidade=[], viaturas_por_status="[]",
                               totais_viaturas={}, unit_color_map={}) # Adicionei unit_color_map vazio aqui para consistência
    finally:
        if cursor:
            cursor.close()
        if conn and not conn.closed:
            conn.close()

# (Seu if __name__ == '__main__': app.run(debug=True) aqui)
if __name__ == '__main__':
    app.run(debug=True)