// static/js/script.js

// Garante que o script só será executado após o DOM estar completamente carregado.
// Isso é crucial para que todos os elementos HTML referenciados existam. <sources>[2,4,5]</sources>
document.addEventListener('DOMContentLoaded', function() {
    // --- Referências a Elementos HTML ---
    // Formulário e campo de input para busca de produto
    const searchForm = document.getElementById('searchForm');
    const barcodeInput = document.getElementById('barcodeInput');

    // Card de detalhes do produto encontrado
    const productDetailsCard = document.getElementById('productDetailsCard');
    const detailCodigoProduto = document.getElementById('detailCodigoProduto');
    const detailNomeProduto = document.getElementById('detailNomeProduto');
    const detailCodigoBarras = document.getElementById('detailCodigoBarras');
    const detailUnidadeVenda = document.getElementById('detailUnidadeVenda');
    const detailMultiplicadorSugerido = document.getElementById('detailMultiplicadorSugerido');

    // Botões de ação no card de detalhes
    const addDefaultLotBtn = document.getElementById('addDefaultLotBtn');
    const selectDifferentLotBtn = document.getElementById('selectDifferentLotBtn');
    // const addManualLotBtn = document.getElementById('addManualLotBtn'); // Removido daqui, agora está na seção de ações da tabela

    // Tabela de produtos contados
    const countedProductsTableBody = document.getElementById('countedProductsTableBody');

    // Botões de ação da tabela
    const generateFileBtn = document.getElementById('generateFileBtn');
    const clearCountedProductsBtn = document.getElementById('clearCountedProductsBtn');
    const addManualLotBtn = document.getElementById('addManualLotBtn'); // NOVO: Referência ao botão movido

    // Modal de seleção de lote (Bootstrap Modal)
    const selectLotModalElement = document.getElementById('selectLotModal');
    const selectLotModal = new bootstrap.Modal(selectLotModalElement); // Instância do modal Bootstrap
    const modalProductName = document.getElementById('modalProductName');
    const modalMultiplicadorSugerido = document.getElementById('modalMultiplicadorSugerido');
    const lotesTableBody = document.getElementById('lotesTableBody');
    const quantityBaseInput = document.getElementById('quantityBaseInput');
    const addSelectedLotBtn = document.getElementById('addSelectedLotBtn');
    const selectLotMessage = document.getElementById('selectLotMessage');
    const addQuickLotModalBtn = document.getElementById('addQuickLotModalBtn'); // NOVO: Botão "Adicionar Rápido (Qtd: 1)" no modal

    // Modal de edição de produto (Bootstrap Modal)
    const editProductModalElement = document.getElementById('editProductModal');
    const editProductModal = new bootstrap.Modal(editProductModalElement); // Instância do modal Bootstrap
    const editProductIdInput = document.getElementById('editProductId');
    const editCodigoProdutoInput = document.getElementById('editCodigoProduto');
    const editNomeProdutoInput = document.getElementById('editNomeProduto');
    const editMultiplicadorInput = document.getElementById('editMultiplicadorInput');
    const editLoteInput = document.getElementById('editLote');
    const editDataFabricacaoInput = document.getElementById('editDataFabricacao');
    const editDataValidadeInput = document.getElementById('editDataValidade');
    const editQuantidadeBaseInput = document.getElementById('editQuantidadeBaseInput');
    const editQuantidadeTotalInput = document.getElementById('editQuantidadeTotalInput');
    const saveEditedProductBtn = document.getElementById('saveEditedProductBtn');

    // Variável para armazenar os detalhes do produto atualmente exibido/selecionado
    let currentProductDetails = null;

    // --- Funções Auxiliares ---

    /**
     * Exibe uma mensagem de alerta na tela.
     * @param {string} message - A mensagem a ser exibida.
     * @param {string} type - O tipo de alerta (e.g., 'success', 'danger', 'warning', 'info').
     */
    function showMessage(message, type) {
        const flashMessagesDiv = document.querySelector('.flash-messages');
        if (flashMessagesDiv) {
            const alertDiv = document.createElement('div');
            alertDiv.classList.add('alert', `alert-${type}`, 'alert-dismissible', 'fade', 'show');
            alertDiv.setAttribute('role', 'alert');
            alertDiv.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            `;
            flashMessagesDiv.appendChild(alertDiv);
            // Remove a mensagem após 5 segundos
            setTimeout(() => {
                bootstrap.Alert.getInstance(alertDiv)?.close();
            }, 5000);
        } else {
            console.warn('Elemento .flash-messages não encontrado para exibir a mensagem:', message);
            alert(`${type.toUpperCase()}: ${message}`); // Fallback para alert()
        }
    }

    /**
     * Busca os detalhes de um produto no backend usando o código de barras.
     * Atualiza o card de detalhes do produto e decide se abre o modal de seleção de lote
     * ou incrementa automaticamente.
     * @param {string} barcode - O código de barras do produto.
     */
    async function fetchProductDetails(barcode) {
        try {
            const formData = new FormData();
            formData.append('barcode', barcode);

            const response = await fetch('/search_product', {
                method: 'POST',
                body: formData
            });
            const data = await response.json();

            if (data.success) {
                currentProductDetails = data; // Armazena os detalhes do produto

                // Atualiza o card de detalhes do produto
                detailCodigoProduto.textContent = data.product.codigo_produto;
                detailNomeProduto.textContent = data.product.nome_produto;
                detailCodigoBarras.textContent = data.product.codigo_barras;
                detailUnidadeVenda.textContent = data.product.unidade_venda;
                detailMultiplicadorSugerido.textContent = data.product.multiplicador_sugerido;
                productDetailsCard.style.display = 'block'; // Exibe o card

                // Lógica de decisão para adição automática ou abertura do modal
                const lastCountedLot = data.last_counted_lot;
                const availableLotes = data.lotes;

                if (lastCountedLot) {
                    // Verifica se o último lote contado ainda está entre os lotes disponíveis do SQL Server
                    const matchingAvailableLot = availableLotes.find(l => 
                        l.lote === lastCountedLot.lote &&
                        l.data_fabricacao === lastCountedLot.data_fabricacao &&
                        l.data_validade === lastCountedLot.data_validade
                    );

                    if (matchingAvailableLot) {
                        // Se o último lote contado ainda existe e está disponível, tenta incrementar
                        await addProductToLastCountedLot(lastCountedLot.id);
                        productDetailsCard.style.display = 'none'; // Oculta o card após a adição automática
                        currentProductDetails = null; // Limpa o produto atual
                        return; // Sai da função, pois a ação já foi realizada
                    }
                }

                // Se não houve adição automática, o card de detalhes permanece visível.
                // Se houver apenas um lote disponível e não houver último lote contado,
                // o botão "Adicionar ao Lote Padrão/Último" cuidará disso.
                // Se houver múltiplos lotes e nenhum último lote, o usuário precisará usar os botões.
                showMessage(`Produto ${data.product.nome_produto} encontrado.`, 'success');

            } else {
                showMessage(data.message, 'danger');
                productDetailsCard.style.display = 'none'; // Oculta o card se o produto não for encontrado
                currentProductDetails = null; // Limpa o produto atual
            }
        } catch (error) {
            console.error('Erro ao buscar produto:', error);
            showMessage('Erro ao conectar com o servidor para buscar produto.', 'danger');
            productDetailsCard.style.display = 'none';
            currentProductDetails = null;
        }
    }

    /**
     * Abre o modal de seleção de lote e preenche com os lotes do produto atual.
     */
    function openSelectLotModal() {
        if (!currentProductDetails || !currentProductDetails.lotes || currentProductDetails.lotes.length === 0) {
            showMessage('Nenhum produto ou lote disponível para seleção. Por favor, busque um produto primeiro.', 'warning');
            return;
        }

        modalProductName.textContent = currentProductDetails.product.nome_produto;
        modalMultiplicadorSugerido.textContent = currentProductDetails.product.multiplicador_sugerido;
        lotesTableBody.innerHTML = ''; // Limpa a tabela de lotes anterior
        selectLotMessage.classList.add('d-none'); // Oculta mensagens de erro anteriores

        currentProductDetails.lotes.forEach((lote, index) => {
            const row = lotesTableBody.insertRow();
            const radioCell = row.insertCell(0);
            const loteCell = row.insertCell(1);
            const fabCell = row.insertCell(2);
            const valCell = row.insertCell(3);
            const saldoCell = row.insertCell(4);

            radioCell.innerHTML = `<input type="radio" name="selectedLot" value="${index}" ${index === 0 ? 'checked' : ''}>`;
            loteCell.textContent = lote.lote;
            fabCell.textContent = lote.data_fabricacao;
            valCell.textContent = lote.data_validade;
            saldoCell.textContent = lote.saldo_disponivel;

            // Destaca lotes com saldo zero ou negativo
            if (lote.saldo_disponivel <= 0) {
                row.classList.add('table-danger'); // Adiciona classe para estilização de perigo
                saldoCell.innerHTML += ' <span class="badge bg-danger">Saldo Zero/Negativo</span>';
            }
        });

        quantityBaseInput.value = 1; // Reseta a quantidade para 1
        selectLotModal.show(); // Exibe o modal
    }

    /**
     * Adiciona o lote selecionado (do modal) à lista de contagem no backend.
     * @param {object} [productDataOverride=null] - Dados do produto/lote para adicionar, se não vier do modal.
     * @param {number} [quantityOverride=null] - Quantidade base a usar, se não vier do input do modal.
     */
    async function addSelectedLotToCount(productDataOverride = null, quantityOverride = null) {
        if (!currentProductDetails) {
            showMessage('Nenhum produto selecionado para adicionar.', 'warning');
            return;
        }

        let selectedLotIndex;
        let quantityBase;

        if (productDataOverride) {
            // Se os dados vêm de um override (ex: botão "Adicionar ao Lote Padrão/Único")
            selectedLotIndex = currentProductDetails.lotes.findIndex(l => 
                l.lote === productDataOverride.lote &&
                l.data_fabricacao === productDataOverride.data_fabricacao &&
                l.data_validade === productDataOverride.data_validade
            );
            quantityBase = productDataOverride.quantidade_base;
        } else {
            // Se os dados vêm do modal de seleção de lote
            const selectedRadio = document.querySelector('input[name="selectedLot"]:checked');
            if (!selectedRadio) {
                showMessage('Por favor, selecione um lote.', 'warning', selectLotMessage);
                return;
            }
            selectedLotIndex = parseInt(selectedRadio.value);
            quantityBase = quantityOverride !== null ? quantityOverride : parseInt(quantityBaseInput.value);
        }

        if (isNaN(quantityBase) || quantityBase <= 0) {
            showMessage('Por favor, insira uma quantidade válida maior que zero.', 'warning', selectLotMessage);
            return;
        }

        const selectedLot = currentProductDetails.lotes[selectedLotIndex];
        if (!selectedLot) {
            showMessage('Lote selecionado inválido.', 'danger', selectLotMessage);
            return;
        }

        // Prepara os dados para enviar ao backend
        const productData = {
            codigo_produto: currentProductDetails.product.codigo_produto,
            codigo_barras: currentProductDetails.product.codigo_barras,
            nome_produto: currentProductDetails.product.nome_produto,
            lote: selectedLot.lote,
            data_fabricacao: selectedLot.data_fabricacao,
            data_validade: selectedLot.data_validade,
            quantidade_base: quantityBase,
            multiplicador_sugerido: currentProductDetails.product.multiplicador_sugerido
        };

        try {
            const response = await fetch('/add_to_selected_lot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(productData)
            });
            const data = await response.json();

            if (data.success) {
                selectLotModal.hide(); // Oculta o modal
                productDetailsCard.style.display = 'none'; // Oculta o card de detalhes
                currentProductDetails = null; // Limpa o produto atual
                updateCountedProductsTable(data.counted_products); // Atualiza a tabela
                showMessage(data.message, 'success');
            } else {
                showMessage(data.message, 'danger', selectLotMessage); // Exibe erro no modal
            }
        } catch (error) {
            console.error('Erro ao adicionar lote selecionado:', error);
            showMessage('Erro ao conectar com o servidor para adicionar lote.', 'danger', selectLotMessage);
        }
    }

    /**
     * Incrementa a quantidade de um item já contado no SQLite.
     * @param {number} countedProductId - O ID do item na tabela ColetaEstoque (SQLite).
     */
    async function addProductToLastCountedLot(countedProductId) {
        try {
            const response = await fetch('/add_to_last_counted_lot', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ id: countedProductId, quantity_to_add: 1 }) // Incrementa 1 unidade base
            });
            const data = await response.json();

            if (data.success) {
                updateCountedProductsTable(data.counted_products);
                showMessage(data.message, 'success');
            } else {
                showMessage(data.message, 'danger');
            }
        } catch (error) {
            console.error('Erro ao adicionar ao último lote contado:', error);
            showMessage('Erro ao conectar com o servidor para adicionar ao último lote.', 'danger');
        }
    }

    /**
     * Atualiza a tabela de produtos contados no frontend.
     * Agrupa os produtos pelo CodigoProduto e lista os lotes abaixo.
     * @param {Array<object>} products - Uma lista de objetos de produtos contados.
     */
    function updateCountedProductsTable(products) {
        countedProductsTableBody.innerHTML = '';
        if (products.length === 0) {
            countedProductsTableBody.innerHTML = `<tr><td colspan="8" class="text-center">Nenhum produto contado ainda.</td></tr>`;
            return;
        }

        let currentCodigoProduto = null;
        let rowCount = 0; // Para numerar as linhas

        products.forEach(product => {
            // Se o código do produto for diferente do anterior, cria uma nova linha de grupo
            if (product.codigo_produto !== currentCodigoProduto) {
                currentCodigoProduto = product.codigo_produto;

                const productGroupRow = countedProductsTableBody.insertRow();
                productGroupRow.classList.add('table-primary', 'fw-bold'); // Estilo para destacar o grupo

                const productCell = productGroupRow.insertCell(0);
                productCell.colSpan = 8; // Ocupa todas as colunas
                productCell.innerHTML = `Produto: ${product.codigo_produto} - ${product.nome_produto} (Cód. Barras: ${product.codigo_barras})`;
            }

            // Adiciona a linha do item de lote individual
            const row = countedProductsTableBody.insertRow();
            row.classList.add('product-item-row'); // Classe para estilização de itens individuais

            row.insertCell(0).textContent = ++rowCount; // Número da linha
            row.insertCell(1).textContent = product.codigo_barras;
            row.insertCell(2).textContent = product.nome_produto;
            row.insertCell(3).textContent = product.lote;
            row.insertCell(4).textContent = product.data_fabricacao;
            row.insertCell(5).textContent = product.data_validade;

            // Exibe a quantidade total e, se houver multiplicador, também a quantidade base x multiplicador
            const qtdText = product.multiplicador_usado && product.multiplicador_usado !== 1 
                            ? `${product.quantidade_total} (${product.quantidade_base} x${product.multiplicador_usado})` 
                            : product.quantidade_total;
            row.insertCell(6).textContent = qtdText;

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
            await fetchProductDetails(barcode); // A lógica de decisão está dentro de fetchProductDetails
            barcodeInput.value = ''; // Limpa o campo de código de barras
            barcodeInput.focus(); // Retorna o foco para o campo para o próximo bip
        } else {
            showMessage('Por favor, insira um código de barras.', 'warning');
        }
    });

    // Evento para o botão "Adicionar ao Lote Padrão/Último" (no card de detalhes)
    addDefaultLotBtn.addEventListener('click', async function() {
        if (!currentProductDetails) {
            showMessage('Nenhum produto selecionado.', 'warning');
            return;
        }

        const lastCountedLot = currentProductDetails.last_counted_lot;
        const availableLotes = currentProductDetails.lotes;

        if (lastCountedLot) {
            // Se há um último lote contado, usa-o para incrementar
            // (A validação de saldo para incremento já ocorre no backend)
            await addProductToLastCountedLot(lastCountedLot.id);
            productDetailsCard.style.display = 'none';
            currentProductDetails = null;
        } else if (availableLotes.length === 1) {
            // Se não há último lote contado, mas só há um lote disponível no SQL Server, adiciona ele automaticamente
            const defaultLot = availableLotes[0];
            const productData = {
                codigo_produto: currentProductDetails.product.codigo_produto,
                codigo_barras: currentProductDetails.product.codigo_barras,
                nome_produto: currentProductDetails.product.nome_produto,
                lote: defaultLot.lote,
                data_fabricacao: defaultLot.data_fabricacao,
                data_validade: defaultLot.data_validade,
                quantidade_base: 1,
                multiplicador_sugerido: currentProductDetails.product.multiplicador_sugerido
            };
            await addSelectedLotToCount(productData);
            productDetailsCard.style.display = 'none';
            currentProductDetails = null;
        } else {
            // Se não há último lote contado e há múltiplos lotes no SQL Server,
            // abre o modal para o usuário escolher.
            openSelectLotModal();
        }
    });

    // Evento para o botão "Adicionar Lote Diferente" (no card de detalhes)
    selectDifferentLotBtn.addEventListener('click', openSelectLotModal);

    // NOVO EVENT LISTENER: Para o botão "Adicionar Lote Manualmente" (agora na seção de ações da tabela)
    addManualLotBtn.addEventListener('click', function() {
        if (!currentProductDetails || !currentProductDetails.lotes || currentProductDetails.lotes.length === 0) {
            showMessage('Por favor, busque um produto com lotes disponíveis primeiro para poder adicionar um lote manualmente.', 'warning');
            return;
        }
        openSelectLotModal(); // Sempre abre o modal de seleção de lote
    });

    // Evento para adicionar o lote selecionado (botão "Adicionar Lote Selecionado" dentro do modal)
    addSelectedLotBtn.addEventListener('click', () => addSelectedLotToCount(null)); // Passa null para indicar que os dados vêm do modal

    // NOVO EVENT LISTENER: Para o botão "Adicionar Rápido (Qtd: 1)" DENTRO DO MODAL
    addQuickLotModalBtn.addEventListener('click', () => addSelectedLotToCount(null, 1)); // Passa null para dados do botão, e 1 para quantityOverride

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
                    currentProductDetails = null; // Limpa o produto atual
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
