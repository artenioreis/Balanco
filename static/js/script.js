// static/js/script.js

// Garante que o script só execute após o DOM estar completamente carregado
document.addEventListener('DOMContentLoaded', function() {
    // --- Referências aos Elementos do DOM ---
    // Formulário de Busca
    const barcodeInput = document.getElementById('barcodeInput');
    const searchForm = document.getElementById('searchForm');
    const searchMessage = document.getElementById('searchMessage');

    // Detalhes do Produto Encontrado
    const productDetailsCard = document.getElementById('productDetailsCard');
    const codigoProdutoInput = document.getElementById('codigoProduto');
    const codigoBarrasInput = document.getElementById('codigoBarras');
    const nomeProdutoInput = document.getElementById('nomeProduto');
    const loteInput = document.getElementById('lote');
    const dataFabricacaoInput = document.getElementById('dataFabricacao');
    const dataValidadeInput = document.getElementById('dataValidade');
    const multiplicadorInput = document.getElementById('multiplicador'); // Campo oculto para o multiplicador sugerido
    const unidadeVendaInput = document.getElementById('unidadeVenda'); // Campo oculto para a unidade de venda

    // Tabela de Produtos Contados
    const countedProductsTableBody = document.getElementById('countedProductsTableBody');
    const generateFileBtn = document.getElementById('generateFileBtn');
    const clearCountedProductsBtn = document.getElementById('clearCountedProductsBtn');

    // Elementos do Modal de Edição
    const editProductModal = new bootstrap.Modal(document.getElementById('editProductModal')); // Instância do modal Bootstrap
    const editProductIdInput = document.getElementById('editProductId');
    const editCodigoProdutoInput = document.getElementById('editCodigoProduto');
    const editNomeProdutoInput = document.getElementById('editNomeProduto');
    const editMultiplicadorInput = document.getElementById('editMultiplicador'); // Multiplicador no modal (agora editável)
    const editLoteInput = document.getElementById('editLote');
    const editDataFabricacaoInput = document.getElementById('editDataFabricacao');
    const editDataValidadeInput = document.getElementById('editDataValidade');
    const editQuantidadeBaseInput = document.getElementById('editQuantidadeBase'); // Quantidade base no modal
    const editQuantidadeTotalInput = document.getElementById('editQuantidadeTotal'); // Quantidade total calculada no modal (somente leitura)
    const saveEditedProductBtn = document.getElementById('saveEditedProductBtn');

    // Variável para armazenar os detalhes do produto atualmente buscado
    let currentProduct = null;

    // --- Funções de Utilidade ---

    /**
     * Exibe uma mensagem de feedback na interface do usuário.
     * @param {string} message - A mensagem a ser exibida.
     * @param {string} type - O tipo de alerta Bootstrap (ex: 'info', 'success', 'danger', 'warning').
     */
    function showMessage(message, type = 'info') {
        searchMessage.innerHTML = `<div class="alert alert-${type}" role="alert">${message}</div>`;
        // Remove a mensagem após 5 segundos
        setTimeout(() => {
            searchMessage.innerHTML = '';
        }, 5000);
    }

    /**
     * Busca os detalhes de um produto no backend usando o código de barras.
     * Preenche o card de detalhes do produto se encontrado.
     * @param {string} barcode - O código de barras a ser buscado.
     * @returns {Promise<boolean>} - True se o produto foi encontrado, False caso contrário.
     */
    async function fetchProductDetails(barcode) {
        try {
            const response = await fetch('/search_product', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded', // Formato para envio de formulário simples
                },
                body: `barcode=${barcode}` // Envia o código de barras no corpo da requisição
            });
            const data = await response.json(); // Converte a resposta para JSON

            if (data.success) {
                currentProduct = data.product; // Armazena os detalhes do produto encontrado
                // Preenche os campos do card de detalhes do produto
                codigoProdutoInput.value = currentProduct.codigo_produto;
                codigoBarrasInput.value = currentProduct.codigo_barras;
                nomeProdutoInput.value = currentProduct.nome_produto;
                loteInput.value = currentProduct.lote || ''; // Usa lote vazio se nulo
                dataFabricacaoInput.value = currentProduct.data_fabricacao || '';
                dataValidadeInput.value = currentProduct.data_validade || '';
                multiplicadorInput.value = currentProduct.multiplicador_sugerido || 1; // Define o multiplicador sugerido
                unidadeVendaInput.value = currentProduct.unidade_venda || 'UN'; // Define a unidade de venda
                productDetailsCard.style.display = 'block'; // Exibe o card de detalhes
                showMessage('Produto encontrado!', 'success');
                return true;
            } else {
                showMessage(data.message, 'danger'); // Exibe mensagem de erro
                productDetailsCard.style.display = 'none'; // Oculta o card de detalhes
                currentProduct = null; // Limpa o produto atual
                return false;
            }
        } catch (error) {
            console.error('Erro ao buscar produto:', error);
            showMessage('Erro ao conectar com o servidor.', 'danger');
            productDetailsCard.style.display = 'none';
            currentProduct = null;
            return false;
        }
    }

    /**
     * Adiciona o produto atualmente selecionado à lista de contagem no backend.
     * @returns {Promise<object|null>} - A resposta JSON do backend ou null em caso de erro.
     */
    async function addCurrentProductToCount() {
        if (!currentProduct) {
            showMessage('Nenhum produto selecionado para adicionar.', 'warning');
            return null;
        }

        // Prepara os dados do produto para enviar ao backend
        const productToAdd = {
            codigo_produto: currentProduct.codigo_produto,
            codigo_barras: currentProduct.codigo_barras,
            nome_produto: currentProduct.nome_produto,
            lote: loteInput.value, // Lote pode ter sido editado pelo usuário
            data_fabricacao: dataFabricacaoInput.value,
            data_validade: dataValidadeInput.value,
            multiplicador_sugerido: multiplicadorInput.value, // Multiplicador sugerido
            unidade_venda: unidadeVendaInput.value // Unidade de venda
        };

        try {
            const response = await fetch('/add_to_count', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json', // Envia dados em formato JSON
                },
                body: JSON.stringify(productToAdd) // Converte o objeto para string JSON
            });
            const data = await response.json();

            if (data.success) {
                updateCountedProductsTable(data.counted_products); // Atualiza a tabela com os novos dados
                // A mensagem agora é exibida no searchForm.addEventListener
                return data; // Retorna a resposta completa para o event listener
            } else {
                showMessage(data.message, 'danger');
                return null;
            }
        } catch (error) {
            console.error('Erro ao adicionar produto à contagem:', error);
            showMessage('Erro ao conectar com o servidor para adicionar produto.', 'danger');
            return null;
        }
    }

    /**
     * Atualiza a tabela de produtos contados na interface do usuário.
     * Agrupa os produtos pelo Código do Produto e exibe os lotes abaixo.
     * @param {Array<object>} products - Uma lista de objetos de produtos contados.
     */
    function updateCountedProductsTable(products) {
        countedProductsTableBody.innerHTML = ''; // Limpa o corpo da tabela
        if (products.length === 0) {
            countedProductsTableBody.innerHTML = `<tr><td colspan="8" class="text-center">Nenhum produto contado ainda.</td></tr>`;
            return;
        }

        let currentCodigoProduto = null; // Variável para controlar o agrupamento por produto

        products.forEach(product => {
            // Se o código do produto mudou (ou é o primeiro item), cria uma nova linha de agrupamento
            if (product.codigo_produto !== currentCodigoProduto) {
                currentCodigoProduto = product.codigo_produto;

                // Cria uma linha de cabeçalho para o grupo de produtos
                const productGroupRow = countedProductsTableBody.insertRow();
                productGroupRow.classList.add('table-primary', 'fw-bold'); // Estilo Bootstrap para destacar

                const productCell = productGroupRow.insertCell(0);
                productCell.colSpan = 8; // Faz a célula ocupar todas as 8 colunas
                productCell.innerHTML = `Produto: ${product.codigo_produto} - ${product.nome_produto} (Cód. Barras: ${product.codigo_barras})`;
            }

            // Cria uma linha para o item de lote específico
            const row = countedProductsTableBody.insertRow();
            row.classList.add('product-item-row'); // Adiciona uma classe para estilização futura, se necessário

            // Preenche as células com os detalhes do lote
            row.insertCell(0).textContent = ''; // Célula vazia para criar uma indentação visual
            row.insertCell(1).textContent = product.codigo_barras;
            row.insertCell(2).textContent = product.nome_produto;
            row.insertCell(3).textContent = product.lote;
            row.insertCell(4).textContent = product.data_fabricacao;
            row.insertCell(5).textContent = product.data_validade;

            // Formata a exibição da quantidade total (base x multiplicador)
            const qtdText = product.multiplicador_usado && product.multiplicador_usado !== 1 
                            ? `${product.quantidade_total} (${product.quantidade_base} x${product.multiplicador_usado})` 
                            : product.quantidade_total;
            row.insertCell(6).textContent = qtdText;

            // Cria a célula para os botões de ação (Editar e Remover)
            const actionsCell = row.insertCell(7);

            // Botão Editar
            const editBtn = document.createElement('button');
            editBtn.textContent = 'Editar';
            editBtn.classList.add('btn', 'btn-sm', 'btn-primary', 'me-2'); // Classes Bootstrap
            editBtn.addEventListener('click', () => openEditModal(product)); // Adiciona evento de clique
            actionsCell.appendChild(editBtn);

            // Botão Remover
            const deleteBtn = document.createElement('button');
            deleteBtn.textContent = 'Remover';
            deleteBtn.classList.add('btn', 'btn-sm', 'btn-danger'); // Classes Bootstrap
            deleteBtn.addEventListener('click', () => deleteProduct(product.id)); // Adiciona evento de clique
            actionsCell.appendChild(deleteBtn);
        });
    }

    /**
     * Carrega a lista de produtos contados do backend e atualiza a tabela.
     */
    async function loadCountedProducts() {
        try {
            const response = await fetch('/get_counted_products');
            const data = await response.json();
            if (data.counted_products) {
                updateCountedProductsTable(data.counted_products);
            }
        } catch (error) {
            console.error('Erro ao carregar produtos contados:', error);
        }
    }

    /**
     * Abre o modal de edição e preenche seus campos com os dados do produto selecionado.
     * @param {object} product - O objeto do produto a ser editado.
     */
    function openEditModal(product) {
        editProductIdInput.value = product.id;
        editCodigoProdutoInput.value = product.codigo_produto;
        editNomeProdutoInput.value = product.nome_produto;
        editMultiplicadorInput.value = product.multiplicador_usado || 1; // Multiplicador usado (pode ser editado)
        editLoteInput.value = product.lote;
        editDataFabricacaoInput.value = product.data_fabricacao;
        editDataValidadeInput.value = product.data_validade;
        editQuantidadeBaseInput.value = product.quantidade_base; // Quantidade base

        updateEditTotalQuantity(); // Calcula e exibe a quantidade total inicial
        editProductModal.show(); // Exibe o modal
    }

    /**
     * Calcula e atualiza o campo de Quantidade Total no modal de edição.
     */
    function updateEditTotalQuantity() {
        const base = parseInt(editQuantidadeBaseInput.value) || 0;
        const mult = parseInt(editMultiplicadorInput.value) || 1;
        editQuantidadeTotalInput.value = base * mult; // Atualiza o campo somente leitura
    }

    /**
     * Salva as alterações de um produto editado no backend.
     */
    saveEditedProductBtn.addEventListener('click', async function() {
        // Coleta os dados editados do modal
        const editedProduct = {
            id: editProductIdInput.value,
            quantidade_base: editQuantidadeBaseInput.value,
            multiplicador_usado: editMultiplicadorInput.value,
            lote: editLoteInput.value,
            data_fabricacao: editDataFabricacaoInput.value,
            data_validade: editDataValidadeInput.value
        };

        try {
            const response = await fetch('/update_counted_product', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(editedProduct)
            });
            const data = await response.json();

            if (data.success) {
                editProductModal.hide(); // Oculta o modal
                loadCountedProducts(); // Recarrega a tabela para mostrar as alterações
                showMessage(data.message, 'success');
            } else {
                showMessage(data.message, 'danger');
            }
        } catch (error) {
            console.error('Erro ao salvar edições:', error);
            showMessage('Erro ao conectar com o servidor para salvar edições.', 'danger');
        }
    });

    /**
     * Remove um produto específico da lista de contagem no backend.
     * @param {number} productId - O ID do produto a ser removido.
     */
    async function deleteProduct(productId) {
        if (confirm('Tem certeza que deseja remover este produto da contagem?')) {
            try {
                const response = await fetch('/delete_counted_product', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ id: productId }) // Envia o ID do produto
                });
                const data = await response.json();

                if (data.success) {
                    loadCountedProducts(); // Recarrega a tabela
                    showMessage(data.message, 'info');
                } else {
                    showMessage(data.message, 'danger');
                }
            } catch (error) {
                console.error('Erro ao remover produto:', error);
                showMessage('Erro ao conectar com o servidor para remover produto.', 'danger');
            }
        }
    }

    // --- Event Listeners ---

    // Evento de submissão do formulário de busca (ao bipar ou digitar e pressionar Enter)
    searchForm.addEventListener('submit', async function(event) {
        event.preventDefault(); // Previne o comportamento padrão de recarregar a página
        const barcode = barcodeInput.value.trim(); // Obtém o valor do código de barras
        if (barcode) {
            const productFound = await fetchProductDetails(barcode); // Busca os detalhes do produto
            if (productFound) {
                const addResponse = await addCurrentProductToCount(); // Adiciona à contagem
                if (addResponse && addResponse.success) {
                    showMessage(addResponse.message, 'success'); // Exibe a mensagem de sucesso do backend
                }
            }
            barcodeInput.value = ''; // Limpa o campo de código de barras
            barcodeInput.focus(); // Retorna o foco para o campo para o próximo bip
        } else {
            showMessage('Por favor, insira um código de barras.', 'warning');
        }
    });

    // Event Listeners para atualizar a quantidade total no modal de edição dinamicamente
    editQuantidadeBaseInput.addEventListener('input', updateEditTotalQuantity);
    editMultiplicadorInput.addEventListener('input', updateEditTotalQuantity);

    // Evento para gerar o arquivo de importação
    generateFileBtn.addEventListener('click', function() {
        window.location.href = '/generate_import_file'; // Redireciona para a rota de geração de arquivo
    });

    // Evento para limpar todos os produtos contados
    clearCountedProductsBtn.addEventListener('click', async function() {
        if (confirm('Tem certeza que deseja limpar TODOS os produtos contados? Esta ação não pode ser desfeita.')) {
            try {
                const response = await fetch('/clear_counted_products', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({}) // Corpo vazio, mas necessário para POST
                });
                const data = await response.json();
                if (data.success) {
                    updateCountedProductsTable([]); // Limpa a tabela no frontend
                    showMessage(data.message, 'info');
                    productDetailsCard.style.display = 'none'; // Oculta detalhes do produto
                    currentProduct = null; // Limpa o produto atual
                } else {
                    showMessage(data.message, 'danger');
                }
            } catch (error) {
                console.error('Erro ao limpar produtos contados:', error);
                showMessage('Erro ao conectar com o servidor para limpar produtos.', 'danger');
            }
        }
    });

    // Carrega os produtos contados ao carregar a página
    loadCountedProducts();
});
