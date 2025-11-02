-- Pre-populate the demo paper with initial LaTeX content
-- This gives the editor visible height from the start

UPDATE research_papers
SET content_json = jsonb_build_object(
    'authoring_mode', 'latex',
    'latex_source', E'\\documentclass{article}
\\usepackage{amsmath}
\\usepackage{graphicx}

\\title{Research Paper}
\\author{}
\\date{}

\\begin{document}

\\maketitle

\\begin{abstract}
Write your abstract here.
\\end{abstract}

\\section{Introduction}

% Start typing your content here


\\end{document}'
)
WHERE id = '90389636-a2cc-4a8d-b7d4-95a52f0f5e1e';

-- Verify the update
SELECT
    id,
    title,
    content_json->>'authoring_mode' as mode,
    length(content_json->>'latex_source') as content_length
FROM research_papers
WHERE id = '90389636-a2cc-4a8d-b7d4-95a52f0f5e1e';
