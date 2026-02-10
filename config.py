# config.py
import os

class Config:
    """
    Classe de configuração para a aplicação Flask.
    Contém configurações gerais e caminhos para outros arquivos de configuração.
    As configurações sensíveis ou que precisam ser alteradas dinamicamente
    (como as do banco de dados) são carregadas de outras fontes.
    """

    # Chave Secreta para segurança da sessão do Flask.
    # É crucial para a segurança da aplicação. Em produção, deve ser
    # gerada de forma robusta e carregada de uma variável de ambiente.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'uma_chave_secreta_muito_forte_e_aleatoria_para_producao_aqui')

    # Caminho para o arquivo JSON que armazenará as configurações do banco de dados.
    # Este arquivo será criado e gerenciado pela interface de usuário.
    # Ele será salvo na mesma pasta onde o 'app.py' está localizado.
    DB_CONFIG_PATH = 'db_config.json'

    # Outras configurações globais da aplicação podem ser adicionadas aqui.
    # Por exemplo:
    # UPLOAD_FOLDER = 'uploads/'
    # MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # Limite de 16MB para uploads
    # DEBUG = True # Definido como True para desenvolvimento, False para produção
    # LOG_FILE_PATH = 'app.log'

    # Exemplo de como você poderia ter diferentes configurações para diferentes ambientes
    # class DevelopmentConfig(Config):
    #     DEBUG = True
    #     # Outras configurações específicas de desenvolvimento

    # class ProductionConfig(Config):
    #     DEBUG = False
    #     # Outras configurações específicas de produção
    #     # SECRET_KEY deve ser carregada de forma mais segura aqui
