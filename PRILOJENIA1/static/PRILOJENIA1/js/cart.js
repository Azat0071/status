/**
 * Корзина STATUS: строки с точкой продаж, проверка остатков, оформление по складам.
 * Строка хранится в localStorage как {productId, storeId, quantity, name, price, image, sku}.
 */
(function (window, document) {
    'use strict';

    const STORAGE_KEY = 'status-cart-v2';
    const LEGACY_KEY = 'status-cart';
    const LAST_ORDERS_KEY = 'status-last-orders';

    const context = window.STATUS_CART_CONTEXT || {};
    const stores = Array.isArray(context.stores) ? context.stores : [];
    const urls = context.urls || {};
    const csrfToken = context.csrfToken || '';
    const currentStoreId = Number(context.currentStoreId) || (stores[0] ? Number(stores[0].id) : 0);

    const storeById = new Map(stores.map((store) => [String(store.id), store]));
    const state = {
        lines: [],
        report: new Map(),
        checkoutId: null,
        isOpen: false,
    };

    const el = (id) => document.getElementById(id);

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, (character) => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        }[character]));
    }

    const rates = context.rates || { KGS: 1, USD: 0.011, EUR: 0.010 };

    function currency() {
        try {
            return localStorage.getItem('status-currency') || 'KGS';
        } catch (error) {
            return 'KGS';
        }
    }

    function money(value) {
        const code = currency();
        const converted = (Number(value) || 0) * (rates[code] || 1);
        if (code === 'USD') return `$${Math.round(converted).toLocaleString('en-US')}`;
        if (code === 'EUR') return `€${Math.round(converted).toLocaleString('en-US')}`;
        return `${Math.round(converted).toLocaleString('ru-RU')} сом`;
    }

    function plural(count, one, few, many) {
        const mod10 = count % 10;
        const mod100 = count % 100;
        if (mod10 === 1 && mod100 !== 11) return one;
        if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
        return many;
    }

    function normalizeLine(line) {
        if (!line || typeof line !== 'object') return null;
        const productId = Number(line.productId ?? line.id);
        const storeId = Number(line.storeId ?? currentStoreId);
        const quantity = Number(line.quantity);
        if (!productId || !storeId || !Number.isFinite(quantity) || quantity < 1) return null;
        return {
            productId,
            storeId,
            quantity: Math.floor(quantity),
            name: line.name || '',
            price: Number(line.price) || 0,
            image: line.image || '',
            sku: line.sku || '',
        };
    }

    function migrateLegacy() {
        let legacy = [];
        try {
            legacy = JSON.parse(localStorage.getItem(LEGACY_KEY) || '[]');
        } catch (error) {
            legacy = [];
        }
        if (!Array.isArray(legacy) || !legacy.length) return [];

        const migrated = legacy
            .map((item) => normalizeLine({ ...item, storeId: currentStoreId }))
            .filter(Boolean);

        localStorage.removeItem(LEGACY_KEY);
        return migrated;
    }

    function load() {
        let stored = [];
        try {
            stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        } catch (error) {
            stored = [];
        }
        if (!Array.isArray(stored) || !stored.length) {
            return migrateLegacy();
        }
        return stored.map(normalizeLine).filter(Boolean);
    }

    function save() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(state.lines));
        } catch (error) {
            console.warn('Не удалось сохранить корзину:', error);
        }
    }

    function lineKey(productId, storeId) {
        return `${productId}:${storeId}`;
    }

    function reportKey(line) {
        return lineKey(line.productId, line.storeId);
    }

    function storeName(storeId) {
        const store = storeById.get(String(storeId));
        return store ? store.name : 'точка закрыта';
    }

    function storeAddress(storeId) {
        const store = storeById.get(String(storeId));
        return store ? store.address : '';
    }

    function totalCount() {
        return state.lines.reduce((sum, line) => sum + line.quantity, 0);
    }

    function groupedLines() {
        const groups = new Map();
        state.lines.forEach((line) => {
            if (!groups.has(line.storeId)) {
                groups.set(line.storeId, {
                    storeId: line.storeId,
                    storeName: storeName(line.storeId),
                    storeAddress: storeAddress(line.storeId),
                    lines: [],
                    total: 0,
                });
            }
            const group = groups.get(line.storeId);
            group.lines.push(line);
            group.total += line.price * line.quantity;
        });
        return Array.from(groups.values());
    }

    function totalPrice() {
        return state.lines.reduce((sum, line) => sum + line.price * line.quantity, 0);
    }

    /* ---------- изменение корзины ---------- */

    function add(payload) {
        const line = normalizeLine({
            ...payload,
            storeId: payload.storeId ?? currentStoreId,
        });
        if (!line) return;

        const existing = state.lines.find(
            (item) => item.productId === line.productId && item.storeId === line.storeId
        );
        const limit = Number(payload.limit) > 0 ? Number(payload.limit) : null;

        if (existing) {
            existing.quantity = limit
                ? Math.min(existing.quantity + line.quantity, limit)
                : existing.quantity + line.quantity;
            existing.name = line.name || existing.name;
            existing.price = line.price || existing.price;
            existing.image = line.image || existing.image;
        } else {
            state.lines.push({
                ...line,
                quantity: limit ? Math.min(line.quantity, limit) : line.quantity,
            });
        }
        save();
        render();
        validate();
    }

    function setQuantity(productId, storeId, quantity) {
        const line = state.lines.find(
            (item) => item.productId === productId && item.storeId === storeId
        );
        if (!line) return;
        const next = Math.floor(quantity);
        if (next < 1) {
            remove(productId, storeId);
            return;
        }
        line.quantity = next;
        save();
        render();
    }

    function remove(productId, storeId) {
        state.lines = state.lines.filter(
            (item) => !(item.productId === productId && item.storeId === storeId)
        );
        state.report.delete(lineKey(productId, storeId));
        save();
        render();
        validate();
    }

    function moveToStore(productId, fromStoreId, toStoreId) {
        const line = state.lines.find(
            (item) => item.productId === productId && item.storeId === fromStoreId
        );
        if (!line) return;
        const target = state.lines.find(
            (item) => item.productId === productId && item.storeId === toStoreId
        );
        if (target) {
            target.quantity += line.quantity;
            state.lines = state.lines.filter((item) => item !== line);
        } else {
            line.storeId = toStoreId;
        }
        save();
        render();
        validate();
    }

    function clear() {
        state.lines = [];
        state.report.clear();
        state.checkoutId = null;
        save();
        render();
    }

    /* ---------- проверка остатков ---------- */

    function validate() {
        if (!state.lines.length) {
            state.report.clear();
            render();
            return Promise.resolve();
        }
        render();
        return fetch(urls.validate, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                items: state.lines.map((line) => ({
                    id: line.productId,
                    store: line.storeId,
                    quantity: line.quantity,
                })),
            }),
        })
            .then((response) => (response.ok ? response.json() : null))
            .then((data) => {
                if (!data || !Array.isArray(data.lines)) return;
                state.report = new Map(
                    data.lines.map((line) => [lineKey(line.product_id, line.store_id), line])
                );
                render();
            })
            .catch(() => {
                /* остатки проверим ещё раз на оформлении */
            });
    }

    function statusFor(line) {
        return state.report.get(reportKey(line)) || null;
    }

    /* ---------- разметка ---------- */

    function lineMarkup(line) {
        const report = statusFor(line);
        const status = report ? report.status : 'ok';
        const available = report ? report.available : null;
        const others = report && Array.isArray(report.others) ? report.others : [];

        const warning = status === 'gone'
            ? `<p class="mt-1 text-[9px] uppercase tracking-[0.14em] text-accent">нет в ${escapeHtml(storeName(line.storeId))}</p>`
            : status === 'short'
                ? `<p class="mt-1 text-[9px] uppercase tracking-[0.14em] text-accent">осталось ${available} из ${line.quantity}</p>`
                : '';

        const moveButton = others.length
            ? `<button type="button" data-cart-move="${line.productId}" data-from="${line.storeId}" data-to="${others[0].store_id}"
                       class="mt-1 text-[9px] uppercase tracking-[0.14em] text-steelGray hover:text-white transition-colors">
                   есть в ${escapeHtml(others[0].store_name)}: ${others[0].total} шт. — переложить
               </button>`
            : '';

        return `
            <div class="flex items-start gap-3">
                <div class="w-12 h-14 bg-obsidian border border-surfaceBorder shrink-0">
                    ${line.image ? `<img src="${escapeHtml(line.image)}" alt="" class="w-full h-full object-cover">` : ''}
                </div>
                <div class="flex-1 min-w-0">
                    <div class="flex items-start justify-between gap-3">
                        <div class="min-w-0">
                            <p class="font-header text-[11px] font-bold uppercase tracking-[0.06em] truncate">${escapeHtml(line.name || 'Товар')}</p>
                            <p class="mt-1 text-[9px] uppercase tracking-[0.14em] text-steelGray">${escapeHtml(storeName(line.storeId))}</p>
                            ${warning}
                            ${moveButton}
                        </div>
                        <p class="font-header text-[11px] font-bold whitespace-nowrap">${money(line.price * line.quantity)}</p>
                    </div>
                    <div class="mt-2 flex items-center gap-2">
                        <div class="flex items-center gap-1">
                            <button type="button" data-cart-dec="${line.productId}" data-store="${line.storeId}" aria-label="Убрать одну единицу"
                                    class="w-6 h-6 bg-obsidian border border-surfaceBorder text-steelGray hover:text-white flex items-center justify-center">−</button>
                            <span class="w-6 text-center text-[11px] font-bold">${line.quantity}</span>
                            <button type="button" data-cart-inc="${line.productId}" data-store="${line.storeId}" aria-label="Добавить единицу"
                                    class="w-6 h-6 bg-obsidian border border-surfaceBorder text-steelGray hover:text-white flex items-center justify-center">+</button>
                        </div>
                        <button type="button" data-cart-remove="${line.productId}" data-store="${line.storeId}"
                                class="ml-auto text-[9px] uppercase tracking-[0.14em] text-steelGray hover:text-white transition-colors">убрать</button>
                    </div>
                </div>
            </div>`;
    }

    function render() {
        const badge = el('cart-count-badge');
        const headerCount = el('cart-count-header');
        const count = totalCount();
        if (badge) {
            badge.textContent = String(count);
            badge.classList.toggle('hidden', count === 0);
        }
        if (headerCount) headerCount.textContent = `(${count})`;

        const empty = el('cart-empty');
        const groupsEl = el('cart-groups');
        const footer = el('cart-footer');
        const totalEl = el('cart-total');
        const checkoutButton = el('cart-checkout');

        if (groupsEl) {
            const groups = groupedLines();
            groupsEl.innerHTML = groups
                .map(
                    (group) => `
                <section class="px-6 py-5 border-b border-surfaceBorder">
                    <div class="flex items-baseline justify-between gap-3">
                        <p class="text-[9px] uppercase tracking-[0.18em] text-white">Самовывоз · ${escapeHtml(group.storeName)}</p>
                        <span class="font-header text-[11px] font-bold">${money(group.total)}</span>
                    </div>
                    <p class="mt-1 text-[9px] text-steelGray">${escapeHtml(group.storeAddress)}</p>
                    <div class="mt-3 space-y-4">
                        ${group.lines.map(lineMarkup).join('')}
                    </div>
                </section>`
                )
                .join('');
        }

        if (empty) empty.classList.toggle('hidden', state.lines.length > 0);
        if (footer) footer.classList.toggle('hidden', state.lines.length === 0);
        if (totalEl) totalEl.textContent = money(totalPrice());
        if (checkoutButton) {
            const groups = groupedLines().length;
            checkoutButton.textContent = groups > 1
                ? `Оформить ${groups} ${plural(groups, 'заказ', 'заказа', 'заказов')}`
                : 'Оформить заказ';
        }
    }

    /* ---------- панель и вкладки ---------- */

    function open(tab) {
        const drawer = el('cart-drawer');
        const backdrop = el('cart-drawer-bg');
        if (!drawer) return;
        drawer.classList.remove('translate-x-full');
        if (backdrop) backdrop.classList.remove('opacity-0', 'pointer-events-none');
        state.isOpen = true;
        selectTab(tab || 'cart');
        validate();
    }

    function close() {
        const drawer = el('cart-drawer');
        const backdrop = el('cart-drawer-bg');
        if (drawer) drawer.classList.add('translate-x-full');
        if (backdrop) backdrop.classList.add('opacity-0', 'pointer-events-none');
        state.isOpen = false;
    }

    function selectTab(tab) {
        const isOrders = tab === 'orders';
        const cartPanel = el('cart-panel');
        const ordersPanel = el('orders-panel');
        const cartTab = el('cart-tab-button');
        const ordersTab = el('orders-tab-button');
        const footer = el('cart-footer');

        if (cartPanel) cartPanel.classList.toggle('hidden', isOrders);
        if (ordersPanel) ordersPanel.classList.toggle('hidden', !isOrders);
        if (footer) footer.classList.toggle('hidden', isOrders || state.lines.length === 0);

        if (cartTab) {
            cartTab.setAttribute('aria-selected', String(!isOrders));
            cartTab.classList.toggle('border-deepBurgundy', !isOrders);
            cartTab.classList.toggle('border-transparent', isOrders);
            cartTab.classList.toggle('text-white', !isOrders);
            cartTab.classList.toggle('text-steelGray', isOrders);
        }
        if (ordersTab) {
            ordersTab.setAttribute('aria-selected', String(isOrders));
            ordersTab.classList.toggle('border-deepBurgundy', isOrders);
            ordersTab.classList.toggle('border-transparent', !isOrders);
            ordersTab.classList.toggle('text-white', isOrders);
            ordersTab.classList.toggle('text-steelGray', !isOrders);
        }
    }

    function openOrders() {
        open('orders');
    }

    /* ---------- оформление ---------- */

    function openCheckout() {
        if (!state.lines.length) return;
        if (!context.isAuthenticated) {
            window.location.href = `${urls.login}?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
            return;
        }
        const modal = el('checkout-modal');
        const summary = el('checkout-summary');
        const error = el('checkout-error');
        if (error) error.classList.add('hidden');
        if (!modal) return;

        if (summary) {
            summary.innerHTML = groupedLines()
                .map(
                    (group) => `
                <div class="border border-surfaceBorder bg-surface p-3">
                    <div class="flex items-baseline justify-between gap-3">
                        <p class="text-[9px] uppercase tracking-[0.16em] text-white">${escapeHtml(group.storeName)}</p>
                        <span class="font-header text-[11px] font-bold">${money(group.total)}</span>
                    </div>
                    <p class="mt-1 text-[9px] text-steelGray">${escapeHtml(group.storeAddress)}</p>
                    <p class="mt-2 text-[10px] text-steelGray">${group.lines.length} ${plural(group.lines.length, 'позиция', 'позиции', 'позиций')}</p>
                </div>`
                )
                .join('');
        }
        close();
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }

    function closeCheckout() {
        const modal = el('checkout-modal');
        if (!modal) return;
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }

    function showConflicts(conflicts) {
        const modal = el('conflict-modal');
        const list = el('conflict-list');
        if (!modal || !list) return;
        list.innerHTML = conflicts
            .map((line) => {
                const move = Array.isArray(line.others) && line.others.length
                    ? `<button type="button" data-conflict-move="${line.product_id}" data-from="${line.store_id}" data-to="${line.others[0].store_id}"
                               class="h-7 px-2 border border-surfaceBorder text-[9px] uppercase tracking-[0.12em] text-white hover:border-accent transition-colors">
                           в ${escapeHtml(line.others[0].store_name)}
                       </button>`
                    : '';
                return `
                <div class="border border-surfaceBorder bg-surface p-3">
                    <p class="font-header text-[11px] font-bold uppercase tracking-[0.06em]">${escapeHtml(line.product_name)}</p>
                    <p class="mt-1 text-[10px] text-steelGray">
                        ${escapeHtml(line.store_name)} · запрошено ${line.requested}, ${line.status === 'gone' ? 'нет в наличии' : `осталось ${line.available}`}
                    </p>
                    <div class="mt-2 flex items-center gap-2">
                        ${move}
                        <button type="button" data-conflict-drop="${line.product_id}" data-store="${line.store_id}"
                                class="h-7 px-2 border border-surfaceBorder text-[9px] uppercase tracking-[0.12em] text-steelGray hover:text-white transition-colors">
                            убрать
                        </button>
                    </div>
                </div>`;
            })
            .join('');
        closeCheckout();
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }

    function closeConflicts() {
        const modal = el('conflict-modal');
        if (!modal) return;
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }

    function submitCheckout(confirmPartial) {
        const addressInput = el('checkout-address');
        const error = el('checkout-error');
        const submit = el('checkout-submit');
        const address = addressInput ? addressInput.value.trim() : '';

        if (!address) {
            if (error) {
                error.textContent = 'Укажите адрес доставки.';
                error.classList.remove('hidden');
            }
            return;
        }
        if (!state.checkoutId) {
            state.checkoutId = (window.crypto && window.crypto.randomUUID)
                ? window.crypto.randomUUID()
                : `chk-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        }
        if (submit) submit.disabled = true;
        if (error) error.classList.add('hidden');

        fetch(urls.createOrder, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                address,
                checkout_id: state.checkoutId,
                confirm_partial: Boolean(confirmPartial),
                items: state.lines.map((line) => ({
                    id: line.productId,
                    store: line.storeId,
                    quantity: line.quantity,
                })),
            }),
        })
            .then((response) => {
                if (response.redirected && response.url.indexOf(urls.login) !== -1) {
                    window.location.href = `${urls.login}?next=${encodeURIComponent(window.location.pathname)}`;
                    return null;
                }
                return response.json().then((data) => ({ status: response.status, data }));
            })
            .then((result) => {
                if (!result) return;
                const { status, data } = result;
                if (status === 409 && Array.isArray(data.conflicts)) {
                    closeCheckout();
                    showConflicts(data.conflicts);
                    return;
                }
                if (status >= 400) {
                    if (error) {
                        error.textContent = data.error || 'Не удалось оформить заказ.';
                        error.classList.remove('hidden');
                    }
                    return;
                }
                const orders = Array.isArray(data.orders) ? data.orders : [];
                closeCheckout();
                clear();
                try {
                    sessionStorage.setItem(LAST_ORDERS_KEY, JSON.stringify(orders));
                } catch (storageError) {
                    /* не критично */
                }
                window.location.href = '/?orders=1';
            })
            .catch(() => {
                if (error) {
                    error.textContent = 'Ошибка сети. Попробуйте ещё раз.';
                    error.classList.remove('hidden');
                }
            })
            .finally(() => {
                if (submit) submit.disabled = false;
            });
    }

    /* ---------- события ---------- */

    function bind() {
        document.querySelectorAll('[data-cart-open]').forEach((button) => {
            button.addEventListener('click', () => open('cart'));
        });

        document.querySelectorAll('[data-cart-add]').forEach((button) => {
            button.addEventListener('click', () => {
                add({
                    id: Number(button.dataset.cartAdd),
                    storeId: Number(button.dataset.cartStore),
                    quantity: 1,
                    name: button.dataset.cartName || '',
                    price: Number(button.dataset.cartPrice) || 0,
                    image: button.dataset.cartImage || '',
                    sku: button.dataset.cartSku || '',
                    limit: Number(button.dataset.cartLimit) || 0,
                });
                open('cart');
            });
        });
        document.querySelectorAll('[data-cart-close]').forEach((button) => {
            button.addEventListener('click', close);
        });
        const cartTab = el('cart-tab-button');
        const ordersTab = el('orders-tab-button');
        if (cartTab) cartTab.addEventListener('click', () => selectTab('cart'));
        if (ordersTab) ordersTab.addEventListener('click', () => selectTab('orders'));

        const checkoutButton = el('cart-checkout');
        if (checkoutButton) checkoutButton.addEventListener('click', openCheckout);
        const checkoutClose = el('checkout-close');
        if (checkoutClose) checkoutClose.addEventListener('click', closeCheckout);
        const checkoutSubmit = el('checkout-submit');
        if (checkoutSubmit) {
            checkoutSubmit.addEventListener('click', () => submitCheckout(false));
        }
        const conflictCancel = el('conflict-cancel');
        if (conflictCancel) conflictCancel.addEventListener('click', closeConflicts);
        const conflictSubmit = el('conflict-submit');
        if (conflictSubmit) conflictSubmit.addEventListener('click', () => submitCheckout(true));

        const groupsEl = el('cart-groups');
        if (groupsEl) {
            groupsEl.addEventListener('click', (event) => {
                const target = event.target.closest('button');
                if (!target) return;
                const productId = Number(target.dataset.cartInc || target.dataset.cartDec || target.dataset.cartRemove || target.dataset.cartMove);
                const storeId = Number(target.dataset.store || target.dataset.from);
                if (!productId || !storeId) return;

                if (target.dataset.cartInc) {
                    const line = state.lines.find((item) => item.productId === productId && item.storeId === storeId);
                    if (line) setQuantity(productId, storeId, line.quantity + 1);
                } else if (target.dataset.cartDec) {
                    const line = state.lines.find((item) => item.productId === productId && item.storeId === storeId);
                    if (line) setQuantity(productId, storeId, line.quantity - 1);
                } else if (target.dataset.cartRemove) {
                    remove(productId, storeId);
                } else if (target.dataset.cartMove) {
                    moveToStore(productId, storeId, Number(target.dataset.to));
                }
            });
        }

        const conflictList = el('conflict-list');
        if (conflictList) {
            conflictList.addEventListener('click', (event) => {
                const target = event.target.closest('button');
                if (!target) return;
                if (target.dataset.conflictDrop) {
                    remove(Number(target.dataset.conflictDrop), Number(target.dataset.store));
                    target.closest('div.border').remove();
                }
                if (target.dataset.conflictMove) {
                    moveToStore(
                        Number(target.dataset.conflictMove),
                        Number(target.dataset.from),
                        Number(target.dataset.to)
                    );
                    closeConflicts();
                    open('cart');
                }
            });
        }

        document.addEventListener('keydown', (event) => {
            if (event.key !== 'Escape') return;
            closeConflicts();
            closeCheckout();
            close();
        });

        window.addEventListener('status-currency', render);
    }

    function showLastOrders() {
        let orders = [];
        try {
            orders = JSON.parse(sessionStorage.getItem(LAST_ORDERS_KEY) || '[]');
        } catch (error) {
            orders = [];
        }
        if (!Array.isArray(orders) || !orders.length) return;
        sessionStorage.removeItem(LAST_ORDERS_KEY);
        const text = orders
            .map((order) => `№${order.id} — ${order.store}`)
            .join(', ');
        window.STATUS_CART_NOTICE = `Оформлено: ${text}`;
    }

    function init() {
        state.lines = load();
        save();
        bind();
        render();
        validate();
    }

    window.STATUS_CART = {
        init,
        add,
        remove,
        setQuantity,
        moveToStore,
        clear,
        open,
        close,
        openOrders,
        openCheckout,
        validate,
        showLastOrders,
        get lines() {
            return state.lines.slice();
        },
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window, document);
