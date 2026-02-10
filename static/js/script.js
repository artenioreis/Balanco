// static/js/script.js
document.addEventListener('DOMContentLoaded', function() {
    const barcodeInput = document.getElementById('barcodeInput');
    const searchForm = document.getElementById('searchForm');
    const searchMessage = document.getElementById('searchMessage');
    const productDetailsCard = document.getElementById('productDetailsCard');
    const codigoProdutoInput = document.getElementById('codigoProduto');
    const codigoBarrasInput = document.getElementById('codigoBarras');
    const nomeProdutoInput = document.getElementById('nomeProduto');
    const loteInput = document.getElementById('lote');
    const dataFabricacaoInput = document.getElementById('dataFabricacao');
    const dataValidadeInput = document.getElementById('dataValidade');
    const multiplicadorSugeridoInput = document.getElementById('multiplicadorSugerido'); // Multiplicador sugerido do DB
    const unidadeVendaInput = document.getElementById('unidadeVenda');
    const countedProductsTableBody = document.getElementById('countedProductsTableBody');
    const generateFileBtn = document.getElementById('generateFileBtn');
    const clearCountedProductsBtn = document.getElementById('clearCountedProductsBtn');

    // Elementos do Modal de Edição
    const editProductModal = new bootstrap.Modal(document.getElementById('editProductModal'));
    const editProductIdInput = document.getElementById('editProductId');
    const editCodigoProdutoInput = document.getElementById('editCodigoProduto');
    const editNomeProdutoInput = document.getElementById('editNomeProduto');
    const editQuantidadeBaseInput = document.getElementById('editQuantidadeBase'); // NOVO: Quantidade de caixas/base
    const editMultiplicadorUsadoInput = document.getElementById('editMultiplicadorUsado'); // NOVO: Multiplicador editável
    const editQuantidadeTotalInput = document.getElementById('editQuantidadeTotal'); // NOVO: Quantidade total calculada
    const editLoteInput = document.getElementById('editLote');
    const editDataFabricacaoInput = document.getElementById('editDataFabricacao');
    const editDataValidadeInput = document.getElementById('editDataValidade');
    const saveEditedProductBtn = document.getElementById('saveEditedProductBtn');

    let currentProduct = null;

    function showMessage(message, type = 'info') {
        searchMessage.innerHTML = `<div class="alert alert-${type}" role="alert">${message}</div>`;
        setTimeout(() => {
            searchMessage.innerHTML = '';
        }, 5000);
    }

    async function fetchProductDetails(barcode) {
        try {
            const response = await fetch('/search_product', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                },
                body: `barcode=${barcode}`
            });
            const data = await response.json();

            if (data.success) {
                currentProduct = data.product;
                codigoProdutoInput.value = currentProduct.codigo_produto;
                codigoBarrasInput.value = currentProduct.codigo_barras;
                nomeProdutoInput.value = currentProduct.nome_produto;
                loteInput.value = currentProduct.lote || '';
                dataFabricacaoInput.value = currentProduct.data_fabricacao || '';
                dataValidadeInput.value = currentProduct.data_validade || '';
                multiplicadorSugeridoInput.value = currentProduct.multiplicador_sugerido || 1; // Multiplicador sugerido
                unidadeVendaInput.value = currentProduct.unidade_venda || 'UN';
                productDetailsCard.style.display = 'block';
                showMessage('Produto encontrado!', 'success');
                return true;
            } else {
                showMessage(data.message, 'danger');
                productDetailsCard.style.display = 'none';
                currentProduct = null;
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

    async function addCurrentProductToCount() {
        if (!currentProduct) {
            showMessage('Nenhum produto selecionado para adicionar.', 'warning');
            return;
        }

        const productToAdd = {
            codigo_produto: currentProduct.codigo_produto,
            codigo_barras: currentProduct.codigo_barras,
            nome_produto: currentProduct.nome_produto,
            lote: loteInput.value,
            data_fabricacao: dataFabricacaoInput.value,
            data_validade: dataValidadeInput.value,
            multiplicador_sugerido: multiplicadorSugeridoInput.value // Envia o sugerido para ser o inicial
        };

        try {
            const response = await fetch('/add_to_count', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(productToAdd)
            });
            const data = await response.json();

            if (data.success) {
                updateCountedProductsTable(data.counted_products);
                showMessage('Produto adicionado/quantidade atualizada!', 'success');
            } else {
                showMessage(data.message, 'danger');
            }
        } catch (error) {
            console.error('Erro ao adicionar produto à contagem:', error);
            showMessage('Erro ao conectar com o servidor para adicionar produto.', 'danger');
        }
    }

    function updateCountedProductsTable(products) {
        countedProductsTableBody.innerHTML = '';
        if (products.length === 0) {
            countedProductsTableBody.innerHTML = `<tr><td colspan="8" class="text-center">Nenhum produto contado ainda.</td></tr>`;
            return;
        }

        products.forEach(product => {
            const row = countedProductsTableBody.insertRow();
            row.insertCell(0).textContent = product.codigo_produto;
            row.insertCell(1).textContent = product.codigo_barras;
            row.insertCell(2).textContent = product.nome_produto;
            row.insertCell(3).textContent = product.lote;
            row.insertCell(4).textContent = product.data_fabricacao;
            row.insertCell(5).textContent = product.data_validade;
            row.insertCell(6).textContent = product.quantidade_total; // Exibe a quantidade total

            const actionsCell = row.insertCell(7);
            const editBtn = document.createElement('button');
            editBtn.textContent = 'Editar';
            editBtn.classList.add('btn', 'btn-sm', 'btn-primary', 'me-2');
            editBtn.addEventListener('click', () => openEditModal(product));
            actionsCell.appendChild(editBtn);

            const deleteBtn = document.createElement('button');
            deleteBtn.textContent = 'Remover';
            deleteBtn.classList.add('btn', 'btn-sm', 'btn-danger');
            deleteBtn.addEventListener('click', () => deleteProduct(product.id));
            actionsCell.appendChild(deleteBtn);
        });
    }

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

    // Função para abrir o modal de edição
    function openEditModal(product) {
        editProductIdInput.value = product.id;
        editCodigoProdutoInput.value = product.codigo_produto;
        editNomeProdutoInput.value = product.nome_produto;
        editQuantidadeBaseInput.value = product.quantidade_base; // Quantidade de caixas/base
        editMultiplicadorUsadoInput.value = product.multiplicador_usado; // Multiplicador usado
        editLoteInput.value = product.lote;
        editDataFabricacaoInput.value = product.data_fabricacao;
        editDataValidadeInput.value = product.data_validade;

        // Calcula e exibe a quantidade total inicial
        editQuantidadeTotalInput.value = product.quantidade_base * product.multiplicador_usado;

        // Adiciona listeners para atualizar a quantidade total dinamicamente
        editQuantidadeBaseInput.oninput = updateEditQuantidadeTotal;
        editMultiplicadorUsadoInput.oninput = updateEditQuantidadeTotal;

        editProductModal.show();
    }

    // Função para atualizar a quantidade total no modal de edição
    function updateEditQuantidadeTotal() {
        const quantidadeBase = parseInt(editQuantidadeBaseInput.value) || 0;
        const multiplicador = parseInt(editMultiplicadorUsadoInput.value) || 0;
        editQuantidadeTotalInput.value = quantidadeBase * multiplicador;
    }

    // Função para salvar as edições
    saveEditedProductBtn.addEventListener('click', async function() {
        const editedProduct = {
            id: editProductIdInput.value,
            quantidade_base: editQuantidadeBaseInput.value, // Envia a quantidade base
            multiplicador_usado: editMultiplicadorUsadoInput.value, // Envia o multiplicador
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
                editProductModal.hide();
                loadCountedProducts();
                showMessage(data.message, 'success');
            } else {
                showMessage(data.message, 'danger');
            }
        } catch (error) {
            console.error('Erro ao salvar edições:', error);
            showMessage('Erro ao conectar com o servidor para salvar edições.', 'danger');
        }
    });

    // Função para remover um produto
    async function deleteProduct(productId) {
        if (confirm('Tem certeza que deseja remover este produto da contagem?')) {
            try {
                const response = await fetch('/delete_counted_product', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ id: productId })
                });
                const data = await response.json();

                if (data.success) {
                    loadCountedProducts();
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

    searchForm.addEventListener('submit', async function(event) {
        event.preventDefault();
        const barcode = barcodeInput.value.trim();
        if (barcode) {
            const productFound = await fetchProductDetails(barcode);
            if (productFound) {
                await addCurrentProductToCount();
            }
            barcodeInput.value = '';
            barcodeInput.focus();
        } else {
            showMessage('Por favor, insira um código de barras.', 'warning');
        }
    });

    generateFileBtn.addEventListener('click', function() {
        window.location.href = '/generate_import_file';
    });

    clearCountedProductsBtn.addEventListener('click', async function() {
        if (confirm('Tem certeza que deseja limpar TODOS os produtos contados? Esta ação não pode ser desfeita.')) {
            try {
                const response = await fetch('/clear_counted_products', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({})
                });
                const data = await response.json();
                if (data.success) {
                    updateCountedProductsTable([]);
                    showMessage(data.message, 'info');
                    productDetailsCard.style.display = 'none';
                    currentProduct = null;
                } else {
                    showMessage(data.message, 'danger');
                }
            } catch (error) {
                console.error('Erro ao limpar produtos contados:', error);
                showMessage('Erro ao conectar com o servidor para limpar produtos.', 'danger');
            }
        }
    });

    loadCountedProducts();
});
