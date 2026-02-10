# app.py

# Importações necessárias para a aplicação Flask
from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for, flash
import pyodbc # Para conectar ao SQL Server (banco de dados principal)
import sqlite3 # Para conectar ao SQLite (banco de dados da coleta local)
from io import StringIO, BytesIO # Para manipulação de arquivos em memória (geração do TXT)
from datetime import datetime, timedelta # Para manipular datas e tempos (formatação, tempo de sessão)
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
# A lista de coleta de produtos agora é armazenada no SQLite, não na sessão.
app.config["SESSION_PERMANENT"] = False # A sessão expira ao fechar o navegador
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30) # Tempo de vida para sessões permanentes (se SESSION_PERMANENT fosse True)

# Caminho para o arquivo de configuração do banco de dados SQL Server (definido em config.py)
DB_CONFIG_FILE = app.config['DB_CONFIG_PATH']
# Lock para garantir que apenas uma thread acesse o arquivo de configuração do DB por vez.
# Isso previne condições de corrida ao ler/escrever o db_config.json.
db_config_lock = threading.Lock()

# --- Configuração do Banco de Dados SQLite para a Coleta ---
# O arquivo SQLite será criado na mesma pasta do app.py.
# Este banco de dados armazenará os produtos coletados de forma centralizada e persistente.
COLLECTION_DB_PATH = 'coleta_estoque.db'

def init_collection_db():
    """
    Inicializa o banco de dados SQLite para a coleta.
    Cria a tabela 'ColetaEstoque' se ela ainda não existir.
    Esta tabela armazena os detalhes dos produtos contados (lote, datas, quantidade, multiplicador).
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
        # Captura e imprime erros específicos do SQLite
        print(f"Erro ao inicializar o banco de dados de coleta SQLite: {e}")
    finally:
        if conn:
            conn.close() # Garante que a conexão seja fechada, mesmo em caso de erro

# Chama a função de inicialização do DB de coleta ao iniciar a aplicação Flask.
# Isso garante que o arquivo 'coleta_estoque.db' e a tabela 'ColetaEstoque' existam
# antes que qualquer rota tente acessá-los.
with app.app_context():
    init_collection_db()

# --- Funções para Gerenciar o Arquivo de Configuração do DB SQL Server ---
def load_db_config():
    """
    Carrega as configurações de conexão do SQL Server de um arquivo JSON (db_config.json).
    Usa um lock para acesso seguro ao arquivo e trata erros de leitura/parsing JSON.
    """
    with db_config_lock:
        if os.path.exists(DB_CONFIG_FILE):
            try:
                with open(DB_CONFIG_FILE, 'r') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                # Erro comum: arquivo JSON corrompido ou mal formatado
                print(f"Erro: Arquivo {DB_CONFIG_FILE} está corrompido ou mal formatado.")
                return None
            except IOError as e:
                # Erro de I/O ao tentar ler o arquivo
                print(f"Erro de I/O ao ler {DB_CONFIG_FILE}: {e}")
                return None
        return None

def save_db_config(config_data):
    """
    Salva as configurações de conexão do SQL Server em um arquivo JSON.
    Usa um lock para acesso seguro ao arquivo e trata erros de escrita.
    """
    with db_config_lock:
        try:
            with open(DB_CONFIG_FILE, 'w') as f:
                json.dump(config_data, f, indent=4) # Salva com indentação para legibilidade
            return True
        except IOError as e:
            # Erro de I/O ao tentar escrever no arquivo
            print(f"Erro ao salvar configurações do DB: {e}")
            return False

def get_sqlserver_connection():
    """
    Estabelece uma conexão com o banco de dados SQL Server usando as configurações salvas.
    Este banco de dados é usado apenas para consulta (leitura) de produtos.
    Trata erros de conexão e credenciais.
    """
    db_config = load_db_config()
    if not db_config:
        print("Erro: Configurações do banco de dados SQL Server não encontradas ou inválidas.")
        flash('As configurações do banco de dados SQL Server não foram encontradas ou estão inválidas. Por favor, configure-as.', 'danger')
        return None

    # Verifica se todas as chaves necessárias estão presentes e não vazias.
    # Isso previne NameError ou KeyError se a configuração estiver incompleta.
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
        # Captura erros específicos do pyodbc (problemas de conexão, credenciais, driver)
        sqlstate = ex.args[0]
        print(f"Erro ao conectar ao banco de dados SQL Server: {sqlstate} - {ex}")
        flash(f'Erro ao conectar ao banco de dados SQL Server: {ex}', 'danger')
        return None
    except Exception as e:
        # Captura quaisquer outros erros inesperados durante a conexão
        print(f"Erro inesperado ao tentar conectar ao banco de dados SQL Server: {e}")
        flash(f'Erro inesperado ao conectar ao banco de dados SQL Server: {e}', 'danger')
        return None

# --- Rotas da Aplicação Flask ---

@app.route('/')
def index():
    """
    Rota principal que renderiza a página inicial da aplicação.
    Redireciona para a página de configurações se o DB SQL Server não estiver configurado,
    garantindo que o usuário configure o acesso antes de usar a funcionalidade principal.
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
    Inclui validação de campos e teste de conexão.
    """
    config_data = load_db_config() # Carrega as configurações atuais para pré-preencher o formulário

    if request.method == 'POST':
        # Coleta os dados do formulário de configurações.
        # Usa .get() para evitar KeyError se um campo estiver faltando.
        server = request.form.get('server')
        database = request.form.get('database')
        username = request.form.get('username')
        password = request.form.get('password')
        driver = request.form.get('driver', '{ODBC Driver 17 for SQL Server}') # Driver padrão com fallback

        new_config = {
            'server': server,
            'database': database,
            'username': username,
            'password': password,
            'driver': driver
        }

        # Valida se todos os campos obrigatórios foram preenchidos.
        # Isso previne erros de conexão com credenciais incompletas.
        if not all([server, database, username, password, driver]):
            flash('Todos os campos de configuração do banco de dados SQL Server são obrigatórios.', 'danger')
            return render_template('settings.html', config=new_config)

        try:
            # Tenta conectar ao SQL Server com as novas configurações para testá-las.
            # Um teste de conexão é crucial para validar as credenciais antes de salvá-las.
            temp_conn_str = (
                f"DRIVER={new_config['driver']};"
                f"SERVER={new_config['server']};"
                f"DATABASE={new_config['database']};"
                f"UID={new_config['username']};"
                f"PWD={new_config['password']}"
            )
            temp_conn = pyodbc.connect(temp_conn_str, timeout=5) # Timeout para não travar a aplicação
            temp_conn.close() # Fecha a conexão de teste imediatamente

            # Se a conexão de teste for bem-sucedida, salva as configurações.
            if save_db_config(new_config):
                flash('Configurações do banco de dados SQL Server salvas e testadas com sucesso!', 'success')
                return redirect(url_for('index')) # Redireciona para a página inicial após sucesso
            else:
                flash('Erro ao salvar as configurações.', 'danger')
        except pyodbc.Error as ex:
            # Captura e exibe erros específicos do pyodbc durante o teste de conexão
            flash(f'Falha ao testar conexão com o banco de dados SQL Server: {ex}', 'danger')
        except Exception as e:
            # Captura outros erros inesperados durante o teste
            flash(f'Erro inesperado ao testar conexão: {e}', 'danger')

        # Se houve erro no POST, renderiza a página de configurações novamente com os dados inseridos
        return render_template('settings.html', config=new_config)

    # Para requisições GET, apenas renderiza a página de configurações com os dados atuais
    return render_template('settings.html', config=config_data)

@app.route('/search_product', methods=['POST'])
def search_product():
    """
    Rota para buscar detalhes de um produto no SQL Server usando o código de barras.
    Retorna uma lista de todos os lotes encontrados para o produto, com seus saldos e multiplicadores.
    Também verifica o último lote contado para este produto no SQLite para otimização do fluxo.
    """
    barcode = request.form.get('barcode')
    if not barcode:
        # Validação de entrada: código de barras é obrigatório
        return jsonify({'success': False, 'message': 'Código de barras não fornecido.'}), 400

    sql_conn = get_sqlserver_connection()
    if not sql_conn:
        # Se não conseguir conectar ao SQL Server, retorna erro.
        return jsonify({'success': False, 'message': 'Não foi possível conectar ao banco de dados SQL Server. Verifique as configurações.'}), 500

    sql_cursor = sql_conn.cursor()
    try:
        # Query SQL para buscar TODOS os lotes de um produto pelo EAN.
        # A condição 'and lt.Qtd_Saldo > 0' foi REMOVIDA para permitir
        # a busca de produtos com saldo zero, conforme solicitado.
        # O multiplicador é inferido usando um CASE na p.Unidade_Venda.
        # Comentários de linha Python (#) foram removidos da string SQL para evitar erros de sintaxe no SQL Server.
        query = """
            SELECT 
                lt.Cod_Produt, 
                Cod_Lote = ISNULL(lt.Cod_Lote, '*'), 
                lt.Dat_Fabric,
                lt.Dat_Vencim, 
                QtdSld = SUM(lt.Qtd_Saldo),         
                p.Descricao, 
                f.Fantasia, 
                dp.Cod_LocFis, 
                p.Unidade_Venda, 
                p.Cod_EAN,
                CASE 
                    WHEN p.Unidade_Venda = 'CX' THEN 30 -- Exemplo: 1 caixa = 30 unidades
                    WHEN p.Unidade_Venda = 'FD' THEN 10 -- Exemplo: 1 fardo = 10 unidades
                    ELSE 1 -- Padrão: 1 unidade
                END AS MultiplicadorUnidade,
                dbo.FN_EAN13Ok(p.Cod_EAN) 
            FROM PRXES pr      
            LEFT JOIN DPXPR dp ON (dp.Cod_Estabe = pr.Cod_Estabe AND dp.Cod_Produt = pr.Cod_Produt)       
            LEFT JOIN PRLOT lt ON (pr.Cod_Estabe = lt.Cod_Estabe AND pr.Cod_Produt = lt.Cod_Produt)       
            LEFT JOIN PRODU p ON (pr.Cod_Produt = p.Codigo)         
            LEFT JOIN FABRI f ON (p.Cod_Fabricante = f.Codigo)      
            WHERE lt.Cod_Estabe = 0
              AND p.Tipo = '00'
              AND p.Cod_EAN = ?
            GROUP BY 
                lt.Cod_Produt, 
                lt.Cod_Lote, 
                lt.Dat_Fabric,
                lt.Dat_Vencim, 
                p.Descricao, 
                f.Fantasia, 
                dp.Cod_LocFis, 
                p.Unidade_Venda, 
                p.Cod_EAN,
                CASE 
                    WHEN p.Unidade_Venda = 'CX' THEN 30
                    WHEN p.Unidade_Venda = 'FD' THEN 10
                    ELSE 1
                END
            ORDER BY Cod_EAN, lt.Cod_Lote, lt.Dat_Fabric, lt.Dat_Vencim
        """
        sql_cursor.execute(query, barcode)
        products_found = sql_cursor.fetchall() # Obtém TODOS os resultados (todos os lotes)

        if not products_found:
            # Se nenhum produto for encontrado no SQL Server, retorna falha.
            return jsonify({'success': False, 'message': 'Produto não encontrado com este código de barras ou critérios.'})

        # Extrai informações comuns do produto (assumindo que são as mesmas para todos os lotes)
        first_product = products_found[0]
        common_product_data = {
            'codigo_produto': first_product.Cod_Produt,
            'codigo_barras': first_product.Cod_EAN,
            'nome_produto': first_product.Descricao,
            'multiplicador_sugerido': first_product.MultiplicadorUnidade,
            'unidade_venda': first_product.Unidade_Venda
        }

        # Lista para armazenar os detalhes de cada lote encontrado no SQL Server
        lotes_data = []
        for product in products_found:
            # Formata as datas para YYYY-MM-DD ou string vazia se NULL
            data_fabricacao_str = product.Dat_Fabric.strftime('%Y-%m-%d') if product.Dat_Fabric else ''
            data_validade_str = product.Dat_Vencim.strftime('%Y-%m-%d') if product.Dat_Vencim else ''
            lotes_data.append({
                'lote': product.Cod_Lote,
                'data_fabricacao': data_fabricacao_str,
                'data_validade': data_validade_str,
                'saldo_disponivel': product.QtdSld # Saldo disponível para este lote
            })

        # --- NOVO: Verificar o último lote contado para este produto no SQLite ---
        # Esta consulta ajuda a otimizar o fluxo de adição no frontend,
        # permitindo o incremento automático se o mesmo lote for bipado novamente.
        last_counted_lot_info = None
        sqlite_conn = None
        try:
            sqlite_conn = sqlite3.connect(COLLECTION_DB_PATH)
            sqlite_cursor = sqlite_conn.cursor()
            sqlite_cursor.execute("""
                SELECT Id, Lote, DataFabricacao, DataValidade, MultiplicadorUsado
                FROM ColetaEstoque
                WHERE CodigoProduto = ?
                ORDER BY DataHoraColeta DESC
                LIMIT 1
            """, (common_product_data['codigo_produto'],))
            last_lot_row = sqlite_cursor.fetchone()
            if last_lot_row:
                last_counted_lot_info = {
                    'id': last_lot_row[0], # ID do item na coleta (SQLite)
                    'lote': last_lot_row[1],
                    'data_fabricacao': last_lot_row[2],
                    'data_validade': last_lot_row[3],
                    'multiplicador_usado': last_lot_row[4]
                }
        except sqlite3.Error as e:
            print(f"Erro ao buscar último lote contado no SQLite: {e}")
            # Não impede a busca principal, apenas loga o erro no console do servidor.
        finally:
            if sqlite_conn:
                sqlite_conn.close()

        # Retorna os dados comuns do produto, a lista de lotes e o último lote contado (se houver)
        return jsonify({
            'success': True, 
            'product': common_product_data, 
            'lotes': lotes_data,
            'last_counted_lot': last_counted_lot_info # Informação do último lote contado no SQLite
        })
    except pyodbc.Error as e:
        # Captura erros específicos do pyodbc ao executar a query SQL Server
        print(f"Erro SQL Server ao buscar produto: {e}")
        return jsonify({'success': False, 'message': f'Erro SQL Server ao buscar produto: {str(e)}'}), 500
    except Exception as e:
        # Captura quaisquer outros erros inesperados
        print(f"Erro inesperado ao buscar produto: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao buscar produto: {str(e)}'}), 500
    finally:
        if sql_conn:
            sql_conn.close()

@app.route('/add_to_selected_lot', methods=['POST'])
def add_to_selected_lot():
    """
    Rota para adicionar uma quantidade específica a um lote selecionado na coleta (SQLite).
    Inclui validação de saldo disponível no SQL Server antes de adicionar.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    # Coleta os dados do produto e lote selecionado enviados pelo frontend
    codigo_produto = data.get('codigo_produto')
    codigo_barras = data.get('codigo_barras')
    nome_produto = data.get('nome_produto')
    lote_selecionado = data.get('lote')
    data_fabricacao_selecionada = data.get('data_fabricacao')
    data_validade_selecionada = data.get('data_validade')

    # Tenta converter quantidade_base e multiplicador para int.
    try:
        quantidade_a_adicionar_base = int(data.get('quantidade_base', 0)) # Quantidade base que o usuário quer adicionar
        multiplicador_sugerido = int(data.get('multiplicador_sugerido', 1))
    except ValueError:
        return jsonify({'success': False, 'message': 'Quantidade base ou multiplicador inválido.'}), 400

    # Valida se todos os campos obrigatórios estão presentes
    if not all([codigo_produto, codigo_barras, nome_produto, lote_selecionado, 
                data_fabricacao_selecionada, data_validade_selecionada]):
        return jsonify({'success': False, 'message': 'Todos os campos do produto e lote são obrigatórios.'}), 400

    # Valida se a quantidade a adicionar é positiva
    if quantidade_a_adicionar_base <= 0:
        return jsonify({'success': False, 'message': 'A quantidade a adicionar deve ser maior que zero.'}), 400

    # --- Validação de Saldo Disponível no SQL Server ---
    # Conecta ao SQL Server para obter o saldo atual do lote.
    sql_conn = get_sqlserver_connection()
    if not sql_conn:
        return jsonify({'success': False, 'message': 'Não foi possível conectar ao banco de dados SQL Server para validar saldo.'}), 500

    sql_cursor = sql_conn.cursor()
    saldo_disponivel = 0
    try:
        # Consulta o saldo atual do lote específico no SQL Server.
        # Usa ISNULL(CONVERT(VARCHAR(10), ..., 120), '') para lidar com datas NULL/vazias
        # de forma segura, evitando erros de conversão de tipo.
        saldo_query = """
            SELECT SUM(lt.Qtd_Saldo) AS Saldo
            FROM PRLOT lt
            JOIN PRODU p ON lt.Cod_Produt = p.Codigo
            WHERE lt.Cod_Estabe = 0
              AND p.Cod_EAN = ?
              AND ISNULL(lt.Cod_Lote, '*') = ?
              AND ISNULL(CONVERT(VARCHAR(10), lt.Dat_Fabric, 120), '') = ?
              AND ISNULL(CONVERT(VARCHAR(10), lt.Dat_Vencim, 120), '') = ?
            GROUP BY lt.Cod_Produt, lt.Cod_Lote, lt.Dat_Fabric, lt.Dat_Vencim
        """
        sql_cursor.execute(saldo_query, 
                           codigo_barras, 
                           lote_selecionado, 
                           data_fabricacao_selecionada, 
                           data_validade_selecionada)
        saldo_result = sql_cursor.fetchone()
        if saldo_result:
            saldo_disponivel = saldo_result.Saldo
    except pyodbc.Error as e:
        print(f"Erro SQL Server ao validar saldo: {e}")
        return jsonify({'success': False, 'message': f'Erro SQL Server ao validar saldo: {str(e)}'}), 500
    except Exception as e:
        print(f"Erro inesperado ao validar saldo no SQL Server: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao validar saldo do lote: {str(e)}'}), 500
    finally:
        if sql_conn:
            sql_conn.close() # Garante que a conexão SQL Server seja fechada

    # Verifica se a quantidade a adicionar excede o saldo disponível.
    if quantidade_a_adicionar_base > saldo_disponivel:
        return jsonify({'success': False, 'message': f'Quantidade a adicionar ({quantidade_a_adicionar_base}) excede o saldo disponível do lote ({saldo_disponivel}).'}), 400

    # --- Adição/Atualização na Coleta SQLite (se validação OK) ---
    # Conecta ao SQLite para registrar a coleta.
    sqlite_conn = None
    try:
        sqlite_conn = sqlite3.connect(COLLECTION_DB_PATH)
        sqlite_cursor = sqlite_conn.cursor()

        # Tenta encontrar um item existente na coleta SQLite com o mesmo produto e lote.
        # A combinação de CodigoProduto, Lote, DataFabricacao e DataValidade define um item único.
        sqlite_cursor.execute("""
            SELECT Id, QuantidadeBase FROM ColetaEstoque
            WHERE CodigoProduto = ? AND Lote = ? AND DataFabricacao = ? AND DataValidade = ?
        """, (codigo_produto, lote_selecionado, data_fabricacao_selecionada, data_validade_selecionada))
        existing_item = sqlite_cursor.fetchone()

        message = ''
        if existing_item:
            # Se o item existe, incrementa a QuantidadeBase.
            new_quantidade_base = existing_item[1] + quantidade_a_adicionar_base
            sqlite_cursor.execute("""
                UPDATE ColetaEstoque SET QuantidadeBase = ?, DataHoraColeta = CURRENT_TIMESTAMP
                WHERE Id = ?
            """, (new_quantidade_base, existing_item[0]))
            sqlite_conn.commit()
            message = f"Quantidade de {nome_produto} (Lote: {lote_selecionado}) atualizada para {new_quantidade_base * multiplicador_sugerido}."
        else:
            # Se o item não existe, insere um novo registro.
            sqlite_cursor.execute("""
                INSERT INTO ColetaEstoque (CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codigo_produto, codigo_barras, nome_produto, lote_selecionado, data_fabricacao_selecionada, data_validade_selecionada, quantidade_a_adicionar_base, multiplicador_sugerido))
            sqlite_conn.commit()
            message = f"Produto {nome_produto} (Lote: {lote_selecionado}) adicionado à coleta."

        # Após a modificação, busca a lista completa e atualizada de produtos coletados.
        # Ordena por CodigoProduto, Lote, DataFabricacao e DataValidade para facilitar o agrupamento no frontend.
        sqlite_cursor.execute("""
            SELECT Id, CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado
            FROM ColetaEstoque ORDER BY CodigoProduto ASC, Lote ASC, DataFabricacao ASC, DataValidade ASC
        """)
        updated_products = []
        for row in sqlite_cursor.fetchall():
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
        if sqlite_conn:
            sqlite_conn.rollback() # Desfaz a transação em caso de erro para manter a integridade
        return jsonify({'success': False, 'message': f'Erro interno ao adicionar produto à coleta: {str(e)}'}), 500
    except Exception as e:
        print(f"Erro inesperado ao adicionar produto à coleta: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao adicionar produto à coleta: {str(e)}'}), 500
    finally:
        if sqlite_conn:
            sqlite_conn.close()

@app.route('/add_to_last_counted_lot', methods=['POST'])
def add_to_last_counted_lot():
    """
    Rota para incrementar a quantidade de um produto no último lote contado.
    Usado para o fluxo otimizado de contagem repetida do mesmo lote.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    item_id = data.get('id') # ID do item na tabela ColetaEstoque
    # Quantidade a adicionar (padrão 1, mas pode ser especificada pelo frontend se necessário)
    quantidade_a_adicionar_base = int(data.get('quantidade_base', 1)) 

    if not item_id:
        return jsonify({'success': False, 'message': 'ID do item de coleta não fornecido.'}), 400
    if quantidade_a_adicionar_base <= 0:
        return jsonify({'success': False, 'message': 'A quantidade a adicionar deve ser maior que zero.'}), 400

    sqlite_conn = None
    try:
        sqlite_conn = sqlite3.connect(COLLECTION_DB_PATH)
        sqlite_cursor = sqlite_conn.cursor()

        # Busca o item existente para obter seus detalhes e a quantidade atual
        sqlite_cursor.execute("""
            SELECT CodigoProduto, CodigoBarras, NomeProduto, QuantidadeBase, MultiplicadorUsado, Lote, DataFabricacao, DataValidade
            FROM ColetaEstoque WHERE Id = ?
        """, (item_id,))
        existing_item = sqlite_cursor.fetchone()

        if not existing_item:
            return jsonify({'success': False, 'message': 'Item de coleta não encontrado para atualização automática.'}), 404

        codigo_produto = existing_item[0]
        codigo_barras = existing_item[1] # Necessário para a validação de saldo
        nome_produto = existing_item[2]
        current_quantidade_base = existing_item[3]
        multiplicador_usado = existing_item[4]
        lote = existing_item[5]
        data_fabricacao = existing_item[6]
        data_validade = existing_item[7]

        new_quantidade_base = current_quantidade_base + quantidade_a_adicionar_base

        # --- Validação de Saldo Disponível no SQL Server para incremento automático ---
        # É crucial revalidar o saldo mesmo no incremento automático para evitar contagens acima do estoque real.
        sql_conn = get_sqlserver_connection()
        if not sql_conn:
            return jsonify({'success': False, 'message': 'Não foi possível conectar ao banco de dados SQL Server para validar saldo.'}), 500

        sql_cursor = sql_conn.cursor()
        saldo_disponivel = 0
        try:
            # Consulta o saldo atual do lote específico no SQL Server.
            # Usa ISNULL(CONVERT(VARCHAR(10), ..., 120), '') para lidar com datas NULL/vazias
            # de forma segura, evitando erros de conversão de tipo.
            saldo_query = """
                SELECT SUM(lt.Qtd_Saldo) AS Saldo
                FROM PRLOT lt
                JOIN PRODU p ON lt.Cod_Produt = p.Codigo
                WHERE lt.Cod_Estabe = 0
                  AND p.Cod_EAN = ? -- Usar CodigoBarras para buscar o lote específico
                  AND ISNULL(lt.Cod_Lote, '*') = ?
                  AND ISNULL(CONVERT(VARCHAR(10), lt.Dat_Fabric, 120), '') = ?
                  AND ISNULL(CONVERT(VARCHAR(10), lt.Dat_Vencim, 120), '') = ?
                GROUP BY lt.Cod_Produt, lt.Cod_Lote, lt.Dat_Fabric, lt.Dat_Vencim
            """
            sql_cursor.execute(saldo_query, 
                               codigo_barras, # Passa o CodigoBarras do item existente
                               lote, 
                               data_fabricacao, 
                               data_validade)
            saldo_result = sql_cursor.fetchone()
            if saldo_result:
                saldo_disponivel = saldo_result.Saldo
        except pyodbc.Error as e:
            print(f"Erro SQL Server ao validar saldo para incremento automático: {e}")
            return jsonify({'success': False, 'message': f'Erro SQL Server ao validar saldo para incremento: {str(e)}'}), 500
        except Exception as e:
            print(f"Erro inesperado ao validar saldo para incremento automático: {e}")
            return jsonify({'success': False, 'message': f'Erro inesperado ao validar saldo para incremento: {str(e)}'}), 500
        finally:
            if sql_conn:
                sql_conn.close()

        # Verifica se a nova quantidade base excede o saldo disponível.
        if new_quantidade_base > saldo_disponivel:
            return jsonify({'success': False, 'message': f'Não foi possível incrementar. A nova quantidade ({new_quantidade_base}) excederia o saldo disponível do lote ({saldo_disponivel}).'}), 400

        # Se a validação de saldo passar, atualiza a quantidade no SQLite.
        sqlite_cursor.execute("""
            UPDATE ColetaEstoque SET QuantidadeBase = ?, DataHoraColeta = CURRENT_TIMESTAMP
            WHERE Id = ?
        """, (new_quantidade_base, item_id))
        sqlite_conn.commit()

        message = f"Quantidade de {nome_produto} (Lote: {lote}) atualizada para {new_quantidade_base * multiplicador_usado}."

        # Retorna a lista completa e atualizada de produtos coletados
        sqlite_cursor.execute("""
            SELECT Id, CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado
            FROM ColetaEstoque ORDER BY CodigoProduto ASC, Lote ASC, DataFabricacao ASC, DataValidade ASC
        """)
        updated_products = []
        for row in sqlite_cursor.fetchall():
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
                'quantidade_total': row[7] * row[8]
            })

        return jsonify({'success': True, 'counted_products': updated_products, 'message': message})
    except sqlite3.Error as e:
        print(f"Erro ao atualizar quantidade no último lote contado: {e}")
        if sqlite_conn:
            sqlite_conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao atualizar quantidade: {str(e)}'}), 500
    except Exception as e:
        print(f"Erro inesperado ao atualizar quantidade no último lote contado: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao atualizar quantidade: {str(e)}'}), 500
    finally:
        if sqlite_conn:
            sqlite_conn.close()

@app.route('/get_counted_products', methods=['GET'])
def get_counted_products():
    """
    Rota para obter todos os produtos atualmente na lista de coleta do SQLite.
    Usado para carregar e atualizar a tabela no frontend.
    """
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        # Seleciona todos os produtos contados, ordenados para facilitar o agrupamento visual no frontend.
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
    except Exception as e:
        print(f"Erro inesperado ao obter produtos da coleta: {e}")
        return jsonify({'counted_products': []}), 500
    finally:
        if conn:
            conn.close()

@app.route('/update_counted_product', methods=['POST'])
def update_counted_product():
    """
    Rota para atualizar um produto contado específico no banco de dados SQLite.
    Permite editar QuantidadeBase, MultiplicadorUsado, Lote, DataFabricacao e DataValidade.
    Inclui validação de entradas.
    """
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    # Coleta os dados editados do frontend.
    item_id = data.get('id')
    lote = data.get('lote')
    data_fabricacao = data.get('data_fabricacao')
    data_validade = data.get('data_validade')

    # Tenta converter quantidade_base e multiplicador para int.
    try:
        quantidade_base = int(data.get('quantidade_base', 0))
        multiplicador_usado = int(data.get('multiplicador_usado', 1))
    except ValueError:
        return jsonify({'success': False, 'message': 'Quantidade base ou multiplicador inválido.'}), 400

    # Valida se todos os campos obrigatórios estão presentes.
    if not all([item_id, lote, data_fabricacao, data_validade]):
        return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios para atualização.'}), 400

    # Valida se quantidade_base e multiplicador_usado são positivos.
    if quantidade_base <= 0 or multiplicador_usado <= 0:
        return jsonify({'success': False, 'message': 'Quantidade base e multiplicador devem ser números positivos.'}), 400

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
    except Exception as e:
        print(f"Erro inesperado ao atualizar produto: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao atualizar produto: {str(e)}'}), 500
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
        return jsonify({'success': False, 'message': 'ID do produto não fornecido.'}), 400

    item_id = data['id']

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ColetaEstoque WHERE Id = ?", (item_id,))
        conn.commit()
        flash('Produto removido da contagem com sucesso!', 'info')
        return jsonify({'success': True, 'message': 'Produto removido.'})
    except sqlite3.Error as e:
        print(f"Erro ao remover produto da coleta SQLite: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao remover produto: {str(e)}'}), 500
    except Exception as e:
        print(f"Erro inesperado ao remover produto: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao remover produto: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/clear_counted_products', methods=['POST'])
def clear_counted_products():
    """
    Rota para limpar todos os produtos da lista de coleta no banco de dados SQLite.
    """
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ColetaEstoque")
        conn.commit()
        flash('Lista de produtos contados limpa com sucesso!', 'info')
        return jsonify({'success': True, 'message': 'Contagem zerada.'})
    except sqlite3.Error as e:
        print(f"Erro ao limpar produtos da coleta SQLite: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao limpar produtos da coleta: {str(e)}'}), 500
    except Exception as e:
        print(f"Erro inesperado ao limpar produtos: {e}")
        return jsonify({'success': False, 'message': f'Erro inesperado ao limpar produtos: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/generate_import_file', methods=['GET'])
def generate_import_file():
    """
    Rota para gerar o arquivo de importação de texto fixo com os produtos coletados.
    Formata os dados conforme o padrão exigido, incluindo espaçamento e datas.
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
            # Desempacota os dados do item do banco de dados
            codigo_produto = item_db[0]
            quantidade_base = item_db[1]
            multiplicador_usado = item_db[2]
            lote = item_db[3]
            data_validade_str = item_db[4]
            data_fabricacao_str = item_db[5]

            quantidade_total = quantidade_base * multiplicador_usado # Calcula a quantidade total

            # Formata DataValidade para DD/MM/YYYY, preenchendo com espaços se inválida/nula
            data_validade_formatada = '          ' # 10 espaços
            if data_validade_str:
                try:
                    data_validade_dt = datetime.strptime(data_validade_str, '%Y-%m-%d')
                    data_validade_formatada = data_validade_dt.strftime('%d/%m/%Y')
                except ValueError:
                    pass # Mantém '          ' se a data for inválida

            # Formata DataFabricacao para DD/MM/YYYY, preenchendo com espaços se inválida/nula
            data_fabricacao_formatada = '          ' # 10 espaços
            if data_fabricacao_str:
                try:
                    data_fabricacao_dt = datetime.strptime(data_fabricacao_str, '%Y-%m-%d')
                    data_fabricacao_formatada = data_fabricacao_dt.strftime('%d/%m/%Y')
                except ValueError:
                    pass # Mantém '          ' se a data for inválida

            # Formata os campos com justificação à esquerda e truncagem para larguras fixas
            codigo_produto_fmt = str(codigo_produto).ljust(14)[:14] # 14 caracteres
            quantidade_produto_fmt = str(quantidade_total).ljust(6)[:6] # 6 caracteres
            lote_produto_fmt = str(lote).ljust(19)[:19] # 19 caracteres

            # Constrói a linha do arquivo com o formato de texto fixo, incluindo o espaço entre as datas
            line = (
                f"{codigo_produto_fmt}"
                f"{quantidade_produto_fmt}"
                f"{lote_produto_fmt}"
                f"{data_validade_formatada} " # Espaço adicionado aqui para separar as datas
                f"{data_fabricacao_formatada}"
            )
            output_text_buffer.write(line + '\n') # Escreve a linha no buffer, seguida de uma nova linha

        csv_string = output_text_buffer.getvalue() # Obtém o conteúdo completo do buffer
        # Codifica para 'latin-1' (ISO-8859-1) que é comum em sistemas legados no Brasil
        output_bytes_buffer = BytesIO(csv_string.encode('latin-1'))
        output_bytes_buffer.seek(0) # Volta para o início do buffer para leitura

        # Envia o arquivo para download
        return send_file(
            output_bytes_buffer,
            mimetype='text/plain', # Tipo MIME para arquivo de texto
            as_attachment=True, # Força o download como anexo
            download_name=f'COLETA_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt' # Nome do arquivo
        )
    except sqlite3.Error as e:
        print(f"Erro ao gerar arquivo de importação do SQLite: {e}")
        flash(f'Erro ao gerar arquivo de importação: {str(e)}', 'danger')
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Erro inesperado ao gerar arquivo de importação: {e}")
        flash(f'Erro inesperado ao gerar arquivo de importação: {str(e)}', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

# Bloco principal para executar a aplicação Flask
if __name__ == '__main__':
    # app.run(debug=True, host='0.0.0.0')
    # Para produção, use um servidor WSGI como Gunicorn ou Waitress.
    # debug=True é útil para desenvolvimento, mas deve ser False em produção.
    # host='0.0.0.0' permite que a aplicação seja acessível de outras máquinas na rede.
    app.run(debug=True, host='0.0.0.0', port=5000) # Porta 5000 é a padrão do Flask
