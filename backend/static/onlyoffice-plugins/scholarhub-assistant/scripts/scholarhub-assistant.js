(function(window, undefined) {
    // Plugin initialization
    let selectedText = '';
    let currentAction = null;
    let processedText = '';

    // DOM elements
    let selectedContentEl, applyBtn, cancelBtn, statusEl;

    // Initialize plugin when ready
    window.Asc.plugin.init = function() {
        console.log('ScholarHub Assistant plugin initialized');
        
        // Initialize DOM elements
        selectedContentEl = document.getElementById('selectedContent');
        applyBtn = document.getElementById('applyBtn');
        cancelBtn = document.getElementById('cancelBtn');
        statusEl = document.getElementById('status');
        
        // Set up event listeners
        setupEventListeners();
        
        // Get initial selection
        updateSelection();
    };

    // Set up event listeners
    function setupEventListeners() {
        // Feature card clicks
        document.querySelectorAll('.feature-card').forEach(card => {
            card.addEventListener('click', function() {
                const action = this.getAttribute('data-action');
                selectFeature(action, this);
            });
        });

        // Button clicks
        applyBtn.addEventListener('click', applyChanges);
        cancelBtn.addEventListener('click', cancelChanges);
    }

    // Handle feature selection
    function selectFeature(action, cardEl) {
        // Remove active class from all cards
        document.querySelectorAll('.feature-card').forEach(c => c.classList.remove('active'));
        
        // Add active class to selected card
        cardEl.classList.add('active');
        
        currentAction = action;
        
        if (selectedText.trim()) {
            processText(action, selectedText);
        } else {
            setStatus('Please select some text in your document first');
        }
    }

    // Process text with AI (simulated for prototype)
    function processText(action, text) {
        if (!text.trim()) {
            setStatus('No text selected');
            return;
        }

        setStatus(`Processing with ${getActionName(action)}...`);
        applyBtn.disabled = true;

        // Simulate AI processing delay
        setTimeout(() => {
            switch (action) {
                case 'summarize':
                    processedText = simulateSummarize(text);
                    break;
                case 'paraphrase':
                    processedText = simulateParaphrase(text);
                    break;
                case 'citations':
                    processedText = simulateCitations(text);
                    break;
                case 'grammar':
                    processedText = simulateGrammarCheck(text);
                    break;
                default:
                    processedText = text;
            }
            
            setStatus(`${getActionName(action)} completed. Click "Apply Changes" to insert.`);
            applyBtn.disabled = false;
            applyBtn.textContent = `Apply ${getActionName(action)}`;
        }, 1500);
    }

    // Simulated AI functions (in real implementation, these would call your backend API)
    function simulateSummarize(text) {
        return `**Summary:** ${text.substring(0, Math.min(100, text.length))}... [This is a simulated AI summary of the selected text]`;
    }

    function simulateParaphrase(text) {
        return `${text.split(' ').reverse().join(' ')} [This is a simulated AI paraphrase]`;
    }

    function simulateCitations(text) {
        return `${text}\n\n**Generated Citations:**\n1. Smith, J. (2023). Example Citation. *Journal of Examples*, 15(3), 123-145.\n2. Doe, A. (2023). Another Reference. *Academic Press*.`;
    }

    function simulateGrammarCheck(text) {
        return text.replace(/\b(teh|adn|thier)\b/g, match => {
            const corrections = { 'teh': 'the', 'adn': 'and', 'thier': 'their' };
            return corrections[match] || match;
        }) + ' [Grammar checked]';
    }

    // Helper functions
    function getActionName(action) {
        const names = {
            'summarize': 'Summary',
            'paraphrase': 'Paraphrase', 
            'citations': 'Citations',
            'grammar': 'Grammar Check'
        };
        return names[action] || action;
    }

    function setStatus(message) {
        statusEl.textContent = message;
    }

    function updateSelection() {
        // Request current selection from OnlyOffice
        window.Asc.plugin.executeMethod("GetSelectedText", null, function(result) {
            if (result && result.trim()) {
                selectedText = result;
                selectedContentEl.textContent = selectedText;
                selectedContentEl.style.fontStyle = 'normal';
            } else {
                selectedText = '';
                selectedContentEl.textContent = 'Select text in your document to use AI features';
                selectedContentEl.style.fontStyle = 'italic';
            }
        });
    }

    // Apply processed changes to document
    function applyChanges() {
        if (!processedText || !currentAction) {
            setStatus('No changes to apply');
            return;
        }

        setStatus('Applying changes to document...');
        
        // Insert the processed text
        window.Asc.plugin.executeMethod("PasteText", [processedText], function() {
            setStatus('Changes applied successfully!');
            
            // Close plugin after a delay
            setTimeout(() => {
                window.Asc.plugin.executeCommand("close", "");
            }, 1500);
        });
    }

    // Cancel and close plugin
    function cancelChanges() {
        window.Asc.plugin.executeCommand("close", "");
    }

    // Handle plugin resize
    window.Asc.plugin.onMethodReturn = function(returnValue) {
        console.log('Method return:', returnValue);
    };

    // Handle selection changes
    window.Asc.plugin.event_onDocumentContentReady = function() {
        updateSelection();
    };

    // Plugin button handlers (for modal buttons defined in config.json)
    window.Asc.plugin.button = function(id) {
        switch(id) {
            case 0: // AI Summarize
                selectFeature('summarize', document.querySelector('[data-action="summarize"]'));
                break;
            case 1: // AI Paraphrase
                selectFeature('paraphrase', document.querySelector('[data-action="paraphrase"]'));
                break;
            case 2: // Generate Citations
                selectFeature('citations', document.querySelector('[data-action="citations"]'));
                break;
            case 3: // Cancel
            default:
                cancelChanges();
                break;
        }
    };

})(window, undefined);