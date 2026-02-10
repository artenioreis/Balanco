# app.py
from flask import Flask, render_template, request, jsonify, session, send_file, redirect, url_for, flash
import pyodbc
import sqlite3
from io import StringIO, BytesIO
from datetime import datetime, timedelta
import json
import os
import threading

from config import Config

app = Flask(__name__)
app.config.from_object(Config)

app.config["SESSION_PERMANENT"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)

DB_CONFIG_FILE = app.config['DB_CONFIG_PATH']
db_config_lock = threading.Lock()

COLLECTION_DB_PATH = 'coleta_estoque.db'

def init_collection_db():
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
        conn.commit()
    except sqlite3.Error as e:
        print(f"Erro ao inicializar o banco de dados de coleta SQLite: {e}")
    finally:
        if conn:
            conn.close()

with app.app_context():
    init_collection_db()

def load_db_config():
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
    with db_config_lock:
        try:
            with open(DB_CONFIG_FILE, 'w') as f:
                json.dump(config_data, f, indent=4)
            return True
        except IOError as e:
            print(f"Erro ao salvar configurações do DB: {e}")
            return False

def get_sqlserver_connection():
    db_config = load_db_config()
    if not db_config:
        print("Erro: Configurações do banco de dados SQL Server não encontradas ou inválidas.")
        flash('As configurações do banco de dados SQL Server não foram encontradas ou estão inválidas. Por favor, configure-as.', 'danger')
        return None

    required_keys = ['server', 'database', 'username', 'password', 'driver']
    if not all(key in db_config and db_config[key] for key in required_keys):
        flash('Algumas configurações do banco de dados SQL Server estão faltando ou vazias. Por favor, verifique.', 'danger')
        return None

    try:
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

@app.route('/')
def index():
    if not load_db_config():
        flash('Por favor, configure o banco de dados SQL Server antes de iniciar a contagem.', 'warning')
        return redirect(url_for('settings'))

    return render_template('index.html')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    config_data = load_db_config()

    if request.method == 'POST':
        server = request.form.get('server')
        database = request.form.get('database')
        username = request.form.get('username')
        password = request.form.get('password')
        driver = request.form.get('driver', '{ODBC Driver 17 for SQL Server}')

        new_config = {
            'server': server,
            'database': database,
            'username': username,
            'password': password,
            'driver': driver
        }

        if not all([server, database, username, password, driver]):
            flash('Todos os campos de configuração do banco de dados SQL Server são obrigatórios.', 'danger')
            return render_template('settings.html', config=new_config)

        try:
            temp_conn_str = (
                f"DRIVER={new_config['driver']};"
                f"SERVER={new_config['server']};"
                f"DATABASE={new_config['database']};"
                f"UID={new_config['username']};"
                f"PWD={new_config['password']}"
            )
            temp_conn = pyodbc.connect(temp_conn_str, timeout=5)
            temp_conn.close()

            if save_db_config(new_config):
                flash('Configurações do banco de dados SQL Server salvas e testadas com sucesso!', 'success')
                return redirect(url_for('index'))
            else:
                flash('Erro ao salvar as configurações.', 'danger')
        except pyodbc.Error as ex:
            flash(f'Falha ao testar conexão com o banco de dados SQL Server: {ex}', 'danger')
        except Exception as e:
            flash(f'Erro inesperado ao testar conexão: {e}', 'danger')

        return render_template('settings.html', config=new_config)

    return render_template('settings.html', config=config_data)

@app.route('/search_product', methods=['POST'])
def search_product():
    barcode = request.form.get('barcode')
    if not barcode:
        return jsonify({'success': False, 'message': 'Código de barras não fornecido.'}), 400

    conn = get_sqlserver_connection()
    if not conn:
        return jsonify({'success': False, 'message': 'Não foi possível conectar ao banco de dados SQL Server. Verifique as configurações.'}), 500

    cursor = conn.cursor()
    try:
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
                    WHEN p.Unidade_Venda = 'CX' THEN 30
                    WHEN p.Unidade_Venda = 'FD' THEN 10
                    ELSE 1
                END AS MultiplicadorUnidade,
                dbo.FN_EAN13Ok(p.Cod_EAN) 
            From PRXES pr      
            Left Join DPXPR dp on (dp.Cod_Estabe = pr.Cod_Estabe And dp.Cod_Produt = pr.Cod_Produt)       
            Left Join PRLOT lt on (pr.Cod_Estabe = lt.Cod_Estabe And pr.Cod_Produt = lt.Cod_Produt)       
            Left Join PRODU p on (pr.Cod_Produt = p.Codigo)         
            Left Join FABRI f on (p.Cod_Fabricante = f.Codigo)      
            Where lt.Cod_Estabe = 0
              -- REMOVIDO: and lt.Qtd_Saldo > 0 para permitir buscar produtos com saldo zero
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
        product = cursor.fetchone()

        if product:
            data_fabricacao_str = product.Dat_Fabric.strftime('%Y-%m-%d') if product.Dat_Fabric else ''
            data_validade_str = product.Dat_Vencim.strftime('%Y-%m-%d') if product.Dat_Vencim else ''

            product_data = {
                'codigo_produto': product.Cod_Produt,
                'codigo_barras': product.Cod_EAN,
                'nome_produto': product.Descricao,
                'lote': product.Cod_Lote,
                'data_fabricacao': data_fabricacao_str,
                'data_validade': data_validade_str,
                'multiplicador_sugerido': product.MultiplicadorUnidade,
                'unidade_venda': product.Unidade_Venda
            }
            return jsonify({'success': True, 'product': product_data})
        else:
            return jsonify({'success': False, 'message': 'Produto não encontrado com este código de barras ou critérios.'})
    except Exception as e:
        print(f"Erro ao buscar produto no SQL Server: {e}")
        return jsonify({'success': False, 'message': f'Erro interno ao buscar produto: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/add_to_count', methods=['POST'])
def add_to_count():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    codigo_produto = data.get('codigo_produto')
    codigo_barras = data.get('codigo_barras')
    nome_produto = data.get('nome_produto')
    lote = data.get('lote')
    data_fabricacao = data.get('data_fabricacao')
    data_validade = data.get('data_validade')
    multiplicador_sugerido = int(data.get('multiplicador_sugerido', 1))

    if not all([codigo_produto, codigo_barras, nome_produto, lote, data_fabricacao, data_validade]):
        return jsonify({'success': False, 'message': 'Todos os campos do produto são obrigatórios para a contagem.'}), 400

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT Id, QuantidadeBase FROM ColetaEstoque
            WHERE CodigoProduto = ? AND Lote = ? AND DataFabricacao = ? AND DataValidade = ?
        """, (codigo_produto, lote, data_fabricacao, data_validade))
        existing_item = cursor.fetchone()

        quantidade_a_adicionar_base = 1 

        if existing_item:
            new_quantidade_base = existing_item[1] + quantidade_a_adicionar_base
            cursor.execute("""
                UPDATE ColetaEstoque SET QuantidadeBase = ?, DataHoraColeta = CURRENT_TIMESTAMP
                WHERE Id = ?
            """, (new_quantidade_base, existing_item[0]))
            conn.commit()
        else:
            cursor.execute("""
                INSERT INTO ColetaEstoque (CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (codigo_produto, codigo_barras, nome_produto, lote, data_fabricacao, data_validade, quantidade_a_adicionar_base, multiplicador_sugerido))
            conn.commit()

        cursor.execute("""
            SELECT Id, CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado
            FROM ColetaEstoque ORDER BY DataHoraColeta DESC
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
                'quantidade_total': row[7] * row[8]
            })

        return jsonify({'success': True, 'counted_products': updated_products})
    except sqlite3.Error as e:
        print(f"Erro ao adicionar produto à coleta SQLite: {e}")
        if conn:
            conn.rollback()
        return jsonify({'success': False, 'message': f'Erro interno ao adicionar produto à coleta: {str(e)}'}), 500
    finally:
        if conn:
            conn.close()

@app.route('/get_counted_products', methods=['GET'])
def get_counted_products():
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT Id, CodigoProduto, CodigoBarras, NomeProduto, Lote, DataFabricacao, DataValidade, QuantidadeBase, MultiplicadorUsado
            FROM ColetaEstoque ORDER BY DataHoraColeta DESC
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
                'quantidade_total': row[7] * row[8]
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
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Dados inválidos.'}), 400

    item_id = data.get('id')
    quantidade_base = data.get('quantidade_base')
    multiplicador_usado = data.get('multiplicador_usado')
    lote = data.get('lote')
    data_fabricacao = data.get('data_fabricacao')
    data_validade = data.get('data_validade')

    if not all([item_id, quantidade_base, multiplicador_usado, lote, data_fabricacao, data_validade]):
        return jsonify({'success': False, 'message': 'Todos os campos são obrigatórios para atualização.'}), 400

    try:
        quantidade_base = int(quantidade_base)
        multiplicador_usado = int(multiplicador_usado)
        if quantidade_base <= 0 or multiplicador_usado <= 0:
            return jsonify({'success': False, 'message': 'Quantidade e multiplicador devem ser números positivos.'}), 400
    except ValueError:
        return jsonify({'success': False, 'message': 'Quantidade ou multiplicador inválido.'}), 400

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
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
    data = request.get_json()
    if not data or 'id' not in data:
        return jsonify({'success': False, 'message': 'ID do item não fornecido.'}), 400

    item_id = data.get('id')

    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
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
    finally:
        if conn:
            conn.close()

@app.route('/generate_import_file', methods=['GET'])
def generate_import_file():
    conn = None
    try:
        conn = sqlite3.connect(COLLECTION_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT CodigoProduto, QuantidadeBase, MultiplicadorUsado, Lote, DataValidade, DataFabricacao
            FROM ColetaEstoque ORDER BY DataHoraColeta ASC
        """)
        counted_products_from_db = cursor.fetchall()

        if not counted_products_from_db:
            flash('Nenhum produto contado para gerar o arquivo.', 'warning')
            return redirect(url_for('index'))

        output_text_buffer = StringIO()

        for item_db in counted_products_from_db:
            codigo_produto = item_db[0]
            quantidade_base = item_db[1]
            multiplicador_usado = item_db[2]
            lote = item_db[3]
            data_validade_str = item_db[4]
            data_fabricacao_str = item_db[5]

            quantidade_total = quantidade_base * multiplicador_usado

            data_validade_formatada = ''
            if data_validade_str:
                try:
                    data_validade_dt = datetime.strptime(data_validade_str, '%Y-%m-%d')
                    data_validade_formatada = data_validade_dt.strftime('%d/%m/%Y')
                except ValueError:
                    data_validade_formatada = '          '
            else:
                data_validade_formatada = '          '

            data_fabricacao_formatada = ''
            if data_fabricacao_str:
                try:
                    data_fabricacao_dt = datetime.strptime(data_fabricacao_str, '%Y-%m-%d')
                    data_fabricacao_formatada = data_fabricacao_dt.strftime('%d/%m/%Y')
                except ValueError:
                    data_fabricacao_formatada = '          '
            else:
                data_fabricacao_formatada = '          '

            codigo_produto_fmt = str(codigo_produto).ljust(14)[:14]
            quantidade_produto_fmt = str(quantidade_total).ljust(6)[:6]
            lote_produto_fmt = str(lote).ljust(19)[:19]

            line = (
                f"{codigo_produto_fmt}"
                f"{quantidade_produto_fmt}"
                f"{lote_produto_fmt}"
                f"{data_validade_formatada} "
                f"{data_fabricacao_formatada}"
            )
            output_text_buffer.write(line + '\n')

        csv_string = output_text_buffer.getvalue()
        output_bytes_buffer = BytesIO(csv_string.encode('latin-1'))
        output_bytes_buffer.seek(0)

        return send_file(
            output_bytes_buffer,
            mimetype='text/plain',
            as_attachment=True,
            download_name=f'COLETA_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        )
    except sqlite3.Error as e:
        print(f"Erro ao gerar arquivo de importação do SQLite: {e}")
        flash(f'Erro ao gerar arquivo de importação: {str(e)}', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
