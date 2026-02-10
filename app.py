# app.py

# Importações necessárias para a aplicação Flask
from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for, flash
import pyodbc # Para conectar ao SQL Server
import sqlite3 # Para conectar ao SQLite (banco de dados da coleta)
from io import StringIO, BytesIO # Para manipulação de arquivos em memória
from datetime import datetime, timedelta # Para manipar datas e tempos
import json # Para ler/escrever arquivos JSON (configurações do DB)
import os # Para interagir com o sistema de arquivos (verificar existência de arquivos)
import threading # Para garantir acesso seguro ao arquivo de configuração do DB

# Importa a classe de configuração do arquivo config.py
from config import Config

# Inicializa a aplicação Flask
app = Flask(__name__)
# Carrega as configurações da classe Config (SECRET_KEY, DB_CONFIG_PATH)
app.config.from_object(Config)

# --- Configuração de Sessão Padrão do Flask (baseada em cookie) ---
# Esta sessão é usada principalmente para armazenar mensagens flash temporárias.
# A lista de coleta de produtos agora é armazenada no SQLite.
app.config["SESSION_PERMANENT"] = False # A sessão expira ao fechar o navegador
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30) # Tempo de vida para sessões permanentes (se SESSION_PERMANENT fosse True)

# Caminho para o arquivo de configuração do banco de dados SQL Server (definido em config.py)
DB_CONFIG_FILE = app.config['DB_CONFIG_PATH']
# Lock para garantir que apenas uma thread acesse o arquivo de configuração do DB por vez
db_config_lock = threading.Lock()

# --- Configuração do Banco de Dados SQLite para a Coleta ---
# O arquivo SQLite será criado na mesma pasta do app.py.
# Este banco de dados armazenará os produtos coletados de forma centralizada.
COLLECTION_DB_PATH = 'coleta_estoque.db'

def init_collection_db():
    """
    Inicializa o banco de dados SQLite para a coleta.
    Cria a tabela 'ColetaEstoque' se ela ainda não existir.
    Esta tabela armazena os detalhes dos produtos contados.
    """
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ColetaEstoque (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                CodigoProduto TEXT NOT NULL,
                CodigoBarras TEXT NOT NULL,
                NomeProduto TEXT NOT NULL,
                Lote TEXT NOT NULL,
                DataFabricacao TEXT NOT NULL,
                DataValidade TEXT NOT NULL,
                QuantidadeBase INTEGER NOT NULL DEFAULT 1,
                MultiplicadorUsado INTEGER NOT NULL DEFAULT 1,
                DataHoraColeta TEXT DEFAULT CURRENT_TIMESTAMP,
                UsuarioColeta TEXT NULL
            )
        """)
        conn.commit() # Confirma as alterações no banco de dados
    except sqlite3.Error as e:
        print(f"Erro ao inicializar o banco de dados de coleta SQLite: {e}")
    finally:
        if conn:
            conn.close() # Garante que a conexão seja fechada

# Chama a função de inicialização do DB de coleta ao iniciar a aplicação Flask.
# Isso garante que o arquivo 'coleta_estoque.db' e a tabela 'ColetaEstoque' existam.
with app.app_context():
    init_collection_db()

# --- Funções para Gerenciar o Arquivo de Configuração do DB SQL Server ---
def load_db_config():
    """
    Carrega as configurações de conexão do SQL Server de um arquivo JSON.
    Usa um lock para acesso seguro ao arquivo.
    """
    with db_config_lock:
        if os.path.exists(DB_CONFIG_FILE):
            try:
                with open(DB_CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print(f"Erro: Arquivo {DB_CONFIG_FILE} está corrompido ou mal formatado.")
                return None
        return None

def save_db_config(config_data):
    """
    Salva as configurações de conexão do SQL Server em um arquivo JSON.
    Usa um lock para acesso seguro ao arquivo.
    """
    with db_config_lock:
        try:
            with open(DB_CONFIG_FILE, 'w') as f:
                json.dump(config_data, f, indent=4) # Salva com indentação para legibilidade
            return True
        except IOError as e:
            print(f"Erro ao salvar configurações do DB: {e}")
            return False

def get_sqlserver_connection():
    """
    Estabelece uma conexão com o banco de dados SQL Server usando as configurações salvas.
    Este banco de dados é usado apenas para consulta (leitura) de produtos.
    """
    db_config = load_db_config()
    if not db_config:
        print("Erro: Configurações do banco de dados SQL Server não encontradas ou inválidas.")
        flash('As configurações do banco de dados SQL Server não foram encontradas ou estão inválidas. Por favor, configure-as.', 'danger')
        return None

    # Verifica se todas as chaves necessárias estão presentes e não vazias
    required_keys = ['server', 'database', 'username', 'password', 'driver']
    if not all(key in db_config and db_config[key] for key in required_keys):
        flash('Algumas configurações do banco de dados SQL Server estão faltando ou vazias. Por favor, verifique.', 'danger')
        return None

    try:
        # Constrói a string de conexão pyodbc
        conn_str = (
            f"DRIVER={db_config.get('driver')};"
            f"SERVER={db_config.get('server')};"
            f"DATABASE={db_config.get('database')};"
            f"UID={db_config.get('username')};"
            f"PWD={db_config.get('password')}"
        )
        conn = pyodbc.connect(conn_str)
        return conn
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        print(f"Erro ao conectar ao banco de dados SQL Server: {sqlstate} - {ex}")
        flash(f'Erro ao conectar ao banco de dados SQL Server: {ex}', 'danger')
        return None
    except Exception as e:
        print(f"Erro inesperado ao tentar conectar ao banco de dados SQL Server: {e}")
        flash(f'Erro inesperado ao conectar ao banco de dados SQL Server: {e}', 'danger')
        return None

# --- Rotas da Aplicação Flask ---

@app.route('/')
def index():
    """
    Rota principal que renderiza a página inicial da aplicação.
    Redireciona para a página de configurações se o DB SQL Server não estiver configurado.
    """
    if not load_db_config():
        flash('Por favor, configure o banco de dados SQL Server antes de iniciar a contagem.', 'warning')
        return redirect(url_for('settings'))

    return render_template('index.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    """
    Rota para configurar as credenciais de conexão do SQL Server.
    Permite ao usuário inserir e testar as configurações do banco de dados.
    """
    config_data = load_db_config() # Carrega as configurações atuais

    if request.method == 'POST':
        # Coleta os dados do formulário de configurações
        server = request.form.get('server')
        database = request.form.get('database')
        username = request.form.get('username')
        password = request.form.get('password')
        driver = request.form.get('driver', '{ODBC Driver 17 for SQL Server}') # Driver padrão

        new_config = {
            'server': server,
            'database': database,
            'username': username,
            'password': password,
            'driver': driver
        }

        # Valida se todos os campos obrigatórios foram preenchidos
        if not all([server, database, username, password, driver]):
            flash('Todos os campos de configuração do banco de dados SQL Server são obrigatórios.', 'danger')
            return render_template('settings.html', config=new_config)

        try:
            # Tenta conectar ao SQL Server com as novas configurações para testá-las
            temp_conn_str = (
                f"DRIVER={new_config['driver']};"
                f"SERVER={new_config['server']};"
                f"DATABASE={new_config['database']};"
                f"UID={new_config['username']};"
                f"PWD={new_config['password']}"
            )
            temp_conn = pyodbc.connect(temp_conn_str, timeout=5) # Timeout para não travar
            temp_conn.close() # Fecha a conexão de teste

            # Se a conexão de teste for bem-sucedida, salva as configurações
            if save_db_config(new_config):
                flash('Configurações do banco de dados SQL Server salvas e testadas com sucesso!', 'success')
                return redirect(url_for('index')) # Redireciona para a página inicial
            else:
                flash('Erro ao salvar as configurações.', 'danger')
        except pyodbc.Error as ex:
            flash(f'Falha ao testar conexão com o banco de dados SQL Server: {ex}', 'danger')
        except Exception as e:
            flash(f'Erro inesperado ao testar conexão: {e}', 'danger')

        return render_template('settings.html', config=new_config)

    # Para requisições GET, apenas renderiza a página de configurações com os dados atuais
    return render_template('settings.html', config=config_data)

@app.route('/search_product', methods=['POST'])
def search_product():
    """
    Rota para buscar detalhes de um produto no SQL Server usando o código de barras.
    Retorna os detalhes do produto, incluindo um multiplicador inferido pela Unidade_Venda.
    """
    barcode = request.form.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'message': 'Código de barras não fornecido.'}), 400

    conn = get_sqlserver_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Não foi possível conectar ao banco de dados SQL Server. Verifique as configurações.'}), 500

    cursor = conn.cursor()
    try:
        # Query SQL para buscar o produto.
        # Importante: A condição 'and lt.Qtd_Saldo > 0' foi REMOVIDA para permitir
        # a busca de produtos com saldo zero, conforme solicitado.
        # O multiplicador é inferido usando um CASE na p.Unidade_Venda,
        # pois a coluna MultiplicadorUnidade não existe no DB principal.
        query = """
            Select Distinct 
                lt.Cod_Produt, 
                Cod_Lote = Isnull(lt.Cod_Lote, '*'), 
                lt.Dat_Fabric,
                lt.Dat_Vencim, 
                QtdSld = sum(lt.Qtd_Saldo),         
                p.Descricao, 
                f.Fantasia, 
                dp.Cod_LocFis, 
                pr.Prc_Venda,
                pr.Prc_CusLiqEnt,
                p.Unidade_Venda, 
                p.Cod_EAN,
                CASE 
                    WHEN p.Unidade_Venda = 'CX' THEN 30 -- Exemplo: 1 caixa = 30 unidades
                    WHEN p.Unidade_Venda = 'FD' THEN 10 -- Exemplo: 1 fardo = 10 unidades
                    ELSE 1 -- Padrão: 1 unidade
                END AS MultiplicadorUnidade,
                dbo.FN_EAN13Ok(p.Cod_EAN) 
            From PRXES pr      
            Left Join DPXPR dp on (dp.Cod_Estabe = pr.Cod_Estabe And dp.Cod_Produt = pr.Cod_Produt)       
            Left Join PRLOT lt on (pr.Cod_Estabe = lt.Cod_Estabe And pr.Cod_Produt = lt.Cod_Produt)       
            Left Join PRODU p on (pr.Cod_Produt = p.Codigo)         
            Left Join FABRI f on (p.Cod_Fabricante = f.Codigo)      
            Where lt.Cod_Estabe = 0
              -- and lt.Qtd_Saldo > 0 -- REMOVIDO para permitir buscar produtos com saldo zero
              And p.Tipo = '00'
              And p.Cod_EAN = ?
            Group by 
                lt.Cod_Produt, 
                lt.Cod_Lote, 
                lt.Dat_Fabric,
                lt.Dat_Vencim, 
                p.Descricao, 
                f.Fantasia, 
                dp.Cod_LocFis, 
                pr.Prc_Venda, 
                pr.Prc_CusLiqEnt,
                p.Unidade_Venda, 
                p.Cod_EAN,
                CASE 
                    WHEN p.Unidade_Venda = 'CX' THEN 30
                    WHEN p.Unidade_Venda = 'FD' THEN 10
                    ELSE 1
                END
            Order By Cod_EAN
        """
        cursor.execute(query, barcode)
        product = cursor.fetchone() # Obtém o primeiro resultado

        if product:
            # Formata as datas para string 'YYYY-MM-DD'
            data_fabricacao_str = product.Dat_Fabric.strftime('%Y-%m-%d') if product.Dat_Fabric else ''
            data_validade_str = product.Dat_Vencim.strftime('%Y-%m-%d') if product.Dat_Vencim else ''

            # Retorna os dados do produto em formato JSON
            product_data = {
                'codigo_produto': product.Cod_Produt,
                'codigo_barras': product.Cod_EAN,
                'nome_produto': product.Descricao,
                'lote': product.Cod_Lote,
                'data_fabricacao': data_fabricacao_str,
                'data_validade': data_validade_str,
                'multiplicador_sugerido': product.MultiplicadorUnidade, # Multiplicador inferido
                'unidade_venda': product.Unidade_Venda # Unidade de venda para exibição
            }
            return jsonify({'success': True, 'product': product_data})
        else:
            return jsonify({'success': False, 'message': 'Produto não encontrado com este código de barras ou critérios.'})
    except Exception as e:
        print(f"Erro ao buscar produto no SQL Server: {e}")
        return jsonify({'success': False, 'message': f'Erro interno ao buscar produto: {str(e)}'}), 500
    finally:
        if conn:
            conn.close() # Garante que a conexão seja fechada

@app.route('/add_to_count', methods=['POST'])
def add_to_count():
    """
    Rota para adicionar ou atualizar um produto na lista de coleta (SQLite).
    Incrementa a QuantidadeBase se o item (produto, lote, datas) já existe,
    ou insere um novo registro.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    # Coleta os dados do produto enviados pelo frontend
    codigo_produto = data.get('codigo_produto')
    codigo_barras = data.get('codigo_barras')
    nome_produto = data.get('nome_produto')
    lote = data.get('lote')
    data_fabricacao = data.get('data_fabricacao')
    data_validade = data.get('data_validade')
    multiplicador_sugerido = int(data.get('multiplicador_sugerido', 1)) # Multiplicador sugerido do produto

    # Valida se todos os campos obrigatórios estão presentes
    if not all([codigo_produto, codigo_barras, nome_produto, lote, data_fabricacao, data_validade]):
        return jsonify({'success': False, 'message': 'Todos os campos do produto são obrigatórios para a contagem.'}), 400

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()

        # Tenta encontrar um item existente com o mesmo CodigoProduto, Lote, DataFabricacao e DataValidade
        cursor.execute("""
            SELECT Id, QuantidadeBase FROM ColetaEstoque
            WHERE CodigoProduto = ? AND Lote = ? AND DataFabricacao = ? AND DataValidade = ?
        """, (codigo_produto, lote, data_fabricacao, data_validade))
        existing_item = cursor.fetchone()

        quantidade_a_adicionar_base = 1 # Sempre adiciona 1 à QuantidadeBase ao bipar
        message = '' # Mensagem de feedback para o usuário

        if existing_item:
            # Se o item existe, incrementa a QuantidadeBase
            new_quantidade_base = existing_item[1] + quantidade_a_adicionar_base
            cursor.execute("""
                UPDATE ColetaEstoque SET QuantidadeBase = ?, DataHoraColeta = CURRENT_TIMESTAMP
                WHERE Id = ?
            """, (new_quantidade_base, existing_item[0]))
            conn.commit()
            message = f"Quantidade de {nome_produto} (Lote: {lote}) atualizada para {new_quantidade_base * multiplicador_sugerido}."
        else:
            # Se o item não existe, insere um novo registro
            cursor.execute("""
                INSERT INTO ColetaEstoque (CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codigo_produto, codigo_barras, nome_produto, lote, data_fabricacao, data_validade, quantidade_a_adicionar_base, multiplicador_sugerido))
            conn.commit()
            message = f"Produto {nome_produto} (Lote: {lote}) adicionado à coleta."

        # Após a modificação, busca a lista completa e atualizada de produtos coletados
        # Ordena por CodigoProduto, Lote, DataFabricacao e DataValidade para facilitar o agrupamento no frontend
        cursor.execute("""
            SELECT Id, CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado
            FROM ColetaEstoque ORDER BY CodigoProduto ASC, Lote ASC, DataFabricacao ASC, DataValidade ASC
        """)
        updated_products = []
        for row in cursor.fetchall():
            updated_products.append({
                'id': row[0],
                'codigo_produto': row[1],
                'codigo_barras': row[2],
                'nome_produto': row[3],
                'lote': row[4],
                'data_fabricacao': row[5],
                'data_validade': row[6],
                'quantidade_base': row[7],
                'multiplicador_usado': row[8],
                'quantidade_total': row[7] * row[8] # Calcula a quantidade total para exibição
            })

        return jsonify({'success': True, 'counted_products': updated_products, 'message': message})
    except sqlite3.Error as e:
        print(f"Erro ao adicionar produto à coleta SQLite: {e}")
        if conn:
            conn.rollback() # Desfaz a transação em caso de erro
        return jsonify({'success': False, 'message': f'Erro interno ao adicionar produto à coleta: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/get_counted_products', methods=['GET'])
def get_counted_products():
    """
    Rota para obter a lista completa de produtos contados do banco de dados SQLite.
    Retorna a lista ordenada para facilitar o agrupamento no frontend.
    """
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        # Seleciona todos os produtos da tabela ColetaEstoque, ordenados para agrupamento
        cursor.execute("""
            SELECT Id, CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado
            FROM ColetaEstoque ORDER BY CodigoProduto ASC, Lote ASC, DataFabricacao ASC, DataValidade ASC
        """)
        products = []
        for row in cursor.fetchall():
            products.append({
                'id': row[0],
                'codigo_produto': row[1],
                'codigo_barras': row[2],
                'nome_produto': row[3],
                'lote': row[4],
                'data_fabricacao': row[5],
                'data_validade': row[6],
                'quantidade_base': row[7],
                'multiplicador_usado': row[8],
                'quantidade_total': row[7] * row[8] # Calcula a quantidade total para exibição
            })
        return jsonify({'counted_products': products})
    except sqlite3.Error as e:
        print(f"Erro ao obter produtos da coleta SQLite: {e}")
        return jsonify({'counted_products': []}), 500
    finally:
        if conn:
            conn.close()

@app.route('/update_counted_product', methods=['POST'])
def update_counted_product():
    """
    Rota para atualizar um produto contado específico no banco de dados SQLite.
    Permite editar QuantidadeBase, MultiplicadorUsado, Lote, DataFabricacao e DataValidade.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    # Coleta os dados editados do frontend
    item_id = data.get('id')
    quantidade_base = data.get('quantidade_base')
    multiplicador_usado = data.get('multiplicador_usado')
    lote = data.get('lote')
    data_fabricacao = data.get('data_fabricacao')
    data_validade = data.get('data_validade')

    # Valida se todos os campos obrigatórios estão presentes
    if not all([item_id, quantidade_base, multiplicador_usado, lote, data_fabricacao, data_validade]):
        return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios para atualização.'}), 400

    try:
        # Converte para inteiro e valida se são positivos
        quantidade_base = int(quantidade_base)
        multiplicador_usado = int(multiplicador_usado)
        if quantidade_base <= 0 or multiplicador_usado <= 0:
            return jsonify({'success': False, 'message': 'Quantidade base e multiplicador devem ser números positivos.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Quantidade base ou multiplicador inválido.'}), 400

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        # Atualiza o registro na tabela ColetaEstoque
        cursor.execute("""
            UPDATE ColetaEstoque SET 
                QuantidadeBase = ?, 
                MultiplicadorUsado = ?, 
                Lote = ?, 
                DataFabricacao = ?, 
                DataValidade = ?, 
                DataHoraColeta = CURRENT_TIMESTAMP
            WHERE Id = ?
        """, (quantidade_base, multiplicador_usado, lote, data_fabricacao, data_validade, item_id))
        conn.commit()
        flash('Produto contado atualizado com sucesso!', 'success')
        return jsonify({'success': True, 'message': 'Produto atualizado.'})
    except sqlite3.Error as e:
        print(f"Erro ao atualizar produto na coleta SQLite: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao atualizar produto: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/delete_counted_product', methods=['POST'])
def delete_counted_product():
    """
    Rota para remover um produto contado específico do banco de dados SQLite.
    """
    data = request.get_json()
    if not data or 'id' not in data:
        return jsonify({'success': False, 'message': 'ID do item não fornecido.'}), 400

    item_id = data.get('id')

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        # Remove o registro da tabela ColetaEstoque com base no Id
        cursor.execute("DELETE FROM ColetaEstoque WHERE Id = ?", (item_id,))
        conn.commit()
        flash('Produto contado removido com sucesso!', 'info')
        return jsonify({'success': True, 'message': 'Produto removido.'})
    except sqlite3.Error as e:
        print(f"Erro ao remover produto da coleta SQLite: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao remover produto: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/clear_counted_products', methods=['POST'])
def clear_counted_products():
    """
    Rota para limpar todos os produtos contados do banco de dados SQLite.
    """
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        # Deleta todos os registros da tabela ColetaEstoque
        cursor.execute("DELETE FROM ColetaEstoque")
        conn.commit()
        flash('Lista de produtos contados limpa com sucesso!', 'info')
        return jsonify({'success': True, 'message': 'Contagem zerada.'})
    except sqlite3.Error as e:
        print(f"Erro ao limpar produtos da coleta SQLite: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao limpar produtos da coleta: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/generate_import_file', methods=['GET'])
def generate_import_file():
    """
    Rota para gerar o arquivo de importação (.txt) com formato de largura fixa.
    Os dados são obtidos do banco de dados SQLite.
    """
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        # Seleciona os dados necessários para o arquivo de importação
        cursor.execute("""
            SELECT CodigoProduto, QuantidadeBase, MultiplicadorUsado, Lote, DataValidade, DataFabricacao
            FROM ColetaEstoque ORDER BY DataHoraColeta ASC
        """)
        counted_products_from_db = cursor.fetchall()

        if not counted_products_from_db:
            flash('Nenhum produto contado para gerar o arquivo.', 'warning')
            return redirect(url_for('index'))

        output_text_buffer = StringIO() # Buffer em memória para construir o arquivo

        for item_db in counted_products_from_db:
            # Desempacota os dados do item do DB (SQLite retorna tuplas)
            codigo_produto = item_db[0]
            quantidade_base = item_db[1]
            multiplicador_usado = item_db[2]
            lote = item_db[3]
            data_validade_str = item_db[4]
            data_fabricacao_str = item_db[5]

            quantidade_total = quantidade_base * multiplicador_usado # Calcula a quantidade total

            # Formata a data de validade para DD/MM/YYYY, preenchendo com espaços se inválida/vazia
            data_validade_formatada = ''
            if data_validade_str:
                try:
                    data_validade_dt = datetime.strptime(data_validade_str, '%Y-%m-%d')
                    data_validade_formatada = data_validade_dt.strftime('%d/%m/%Y')
                except ValueError:
                    data_validade_formatada = '          ' # 10 espaços
            else:
                data_validade_formatada = '          ' # 10 espaços

            # Formata a data de fabricação para DD/MM/YYYY, preenchendo com espaços se inválida/vazia
            data_fabricacao_formatada = ''
            if data_fabricacao_str:
                try:
                    data_fabricacao_dt = datetime.strptime(data_fabricacao_str, '%Y-%m-%d')
                    data_fabricacao_formatada = data_fabricacao_dt.strftime('%d/%m/%Y')
                except ValueError:
                    data_fabricacao_formatada = '          ' # 10 espaços
            else:
                data_fabricacao_formatada = '          ' # 10 espaços

            # Formata os campos para as larguras fixas especificadas
            codigo_produto_fmt = str(codigo_produto).ljust(14)[:14] # 14 caracteres, alinhado à esquerda
            quantidade_produto_fmt = str(quantidade_total).ljust(6)[:6] # 6 caracteres, alinhado à esquerda
            lote_produto_fmt = str(lote).ljust(19)[:19] # 19 caracteres, alinhado à esquerda

            # Constrói a linha do arquivo com os campos formatados e o espaço entre as datas
            line = (
                f"{codigo_produto_fmt}"
                f"{quantidade_produto_fmt}"
                f"{lote_produto_fmt}"
                f"{data_validade_formatada} " # Espaço adicionado aqui para separar as datas
                f"{data_fabricacao_formatada}"
            )
            output_text_buffer.write(line + '\n') # Escreve a linha no buffer, seguida de uma nova linha

        csv_string = output_text_buffer.getvalue() # Obtém o conteúdo completo do buffer
        output_bytes_buffer = BytesIO(csv_string.encode('latin-1')) # Codifica para latin-1 (comum em sistemas legados)
        output_bytes_buffer.seek(0) # Volta para o início do buffer

        # Envia o arquivo para download
        return send_file(
            output_bytes_buffer,
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'COLETA_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt' # Nome do arquivo com timestamp
        )
    except sqlite3.Error as e:
        print(f"Erro ao gerar arquivo de importação do SQLite: {e}")
        flash(f'Erro ao gerar arquivo de importação: {str(e)}', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

# Inicia o servidor Flask em modo debug, acessível de qualquer IP (0.0.0.0)
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
