// The following logic provides auto-scroll behavior for the chat messages list.
// If you don't want that behavior, you can simply not load this module.

window.customElements.define('chat-messages', class ChatMessages extends HTMLElement {
    static _isFirstAutoScroll = true;

    connectedCallback() {
        this._observer = new MutationObserver(mutations => this._scheduleAutoScroll(mutations));
        this._observer.observe(this, { childList: true, attributes: true });
    }

    disconnectedCallback() {
        this._observer.disconnect();
    }

    _scheduleAutoScroll(mutations) {
        // Debounce the calls in case multiple DOM updates occur together
        cancelAnimationFrame(this._nextAutoScroll);
        this._nextAutoScroll = requestAnimationFrame(() => {
            const addedUserMessage = mutations.some(m => Array.from(m.addedNodes).some(n => n.parentElement === this && n.classList?.contains('user-message')));
            const elem = this.lastElementChild;
            if (ChatMessages._isFirstAutoScroll || addedUserMessage || this._elemIsNearScrollBoundary(elem, 300)) {
                elem.scrollIntoView({ behavior: ChatMessages._isFirstAutoScroll ? 'instant' : 'smooth' });
                ChatMessages._isFirstAutoScroll = false;
            }
        });
    }

    _elemIsNearScrollBoundary(elem, threshold) {
        const maxScrollPos = document.body.scrollHeight - window.innerHeight;
        const remainingScrollDistance = maxScrollPos - window.scrollY;
        return remainingScrollDistance < elem.offsetHeight + threshold;
    }
});
