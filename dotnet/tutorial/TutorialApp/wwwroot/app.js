window.highlightCode = () => {
    if (typeof hljs !== 'undefined') {
        hljs.highlightAll();
    }
};

window.getStoredLanguage = () => {
    return localStorage.getItem('maf-tutorial-lang') ?? 'en';
};

window.setStoredLanguage = (code) => {
    localStorage.setItem('maf-tutorial-lang', code);
};
