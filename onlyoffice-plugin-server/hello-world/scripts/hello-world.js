(function(window, undefined) {

    window.Asc.plugin.init = function() {
        console.log('Hello World Plugin initialized via developer console!');
    };

    window.Asc.plugin.button = function(id) {
        console.log('Button clicked:', id);
        
        if (id === 0) {
            console.log('Inserting Hello World text...');
            
            // Method 1: Using serialized script (from documentation)
            var sScript = "var oDocument = Api.GetDocument();";
            sScript += "var oParagraph = Api.CreateParagraph();";
            sScript += "oParagraph.AddText('Hello World from ScholarHub OnlyOffice Plugin! 🎓 (via Developer Console)');";
            sScript += "oDocument.InsertContent([oParagraph]);";
            
            this.executeCommand("script", sScript);
            console.log('Script executed:', sScript);
        }
        
        // Close plugin
        this.executeCommand("close", "");
    };

})(window, undefined);