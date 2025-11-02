// Hello World Plugin - Debug Version
(function(window, undefined){
    
    console.log('🚀 Plugin script loaded!');
    
    var text = "Hello world from ScholarHub! 🎓";

    window.Asc.plugin.init = function()
    {
        console.log('🎯 Plugin init called!');
        
        try {
            // Try the simplest method first - serialize command as text
            var sScript = "var oDocument = Api.GetDocument();";
            sScript += "var oParagraph = Api.CreateParagraph();";
            sScript += "oParagraph.AddText('Hello world from ScholarHub! 🎓');";
            sScript += "oDocument.InsertContent([oParagraph]);";
            
            console.log('📝 Executing script:', sScript);
            this.info.recalculate = true;
            this.executeCommand("close", sScript);
            console.log('✅ Script executed successfully');
            
        } catch (error) {
            console.error('❌ Error in script execution:', error);
            
            // Fallback: try callCommand method
            try {
                console.log('🔄 Trying callCommand fallback...');
                this.callCommand(function() {
                    console.log('📄 Inside callCommand');
                    var oDocument = Api.GetDocument();
                    console.log('📄 Document:', !!oDocument);
                    var oParagraph = Api.CreateParagraph();
                    oParagraph.AddText("Hello world from ScholarHub! 🎓");
                    oDocument.InsertContent([oParagraph]);
                    console.log('✅ CallCommand executed');
                }, true);
            } catch (fallbackError) {
                console.error('❌ Fallback also failed:', fallbackError);
            }
        }
    };

    window.Asc.plugin.button = function(id)
    {
        console.log('🔘 Button called with id:', id);
        
        // Try to insert text when button is clicked too
        try {
            this.callCommand(function() {
                var oDocument = Api.GetDocument();
                var oParagraph = Api.CreateParagraph();
                oParagraph.AddText("Hello from button click! 🎓");
                oDocument.InsertContent([oParagraph]);
            }, true);
            console.log('✅ Button insertion successful');
        } catch (error) {
            console.error('❌ Button insertion failed:', error);
        }
    };

    // Add event listeners for debugging
    window.Asc.plugin.onMethodReturn = function(returnValue) {
        console.log('📤 Method returned:', returnValue);
    };

    console.log('🏁 Plugin script setup complete');

})(window, undefined);