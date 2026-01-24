"""
Test template conversion with a large, realistic academic paper.
"""
import sys
import os
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env'))

from app.services.smart_agent_service_v2 import SmartAgentServiceV2
from app.constants.paper_templates import CONFERENCE_TEMPLATES

# Large realistic academic paper (500+ lines)
HUGE_DOC = r"""
\documentclass[12pt,letterpaper]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{graphicx}
\usepackage{hyperref}
\usepackage{natbib}
\usepackage{algorithm}
\usepackage{algorithmic}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{xcolor}
\usepackage{subcaption}
\usepackage{tikz}
\usetikzlibrary{shapes,arrows,positioning}

\newtheorem{theorem}{Theorem}
\newtheorem{lemma}[theorem]{Lemma}
\newtheorem{proposition}[theorem]{Proposition}
\newtheorem{corollary}[theorem]{Corollary}
\newtheorem{definition}{Definition}

\title{Efficient Sparse Attention Mechanisms for Large-Scale Language Model Pre-training}
\author{
    Alexandra Chen\thanks{Corresponding author: achen@stanford.edu}\\
    Department of Computer Science\\
    Stanford University\\
    Stanford, CA 94305, USA
    \and
    Marcus Johnson\\
    Google DeepMind\\
    London, UK
    \and
    Sarah Williams\\
    Department of Statistics\\
    MIT\\
    Cambridge, MA 02139, USA
    \and
    David Park\\
    Meta AI Research\\
    Menlo Park, CA, USA
}
\date{January 2024}

\begin{document}
\maketitle

\begin{abstract}
Large language models (LLMs) have demonstrated remarkable capabilities across a wide range of natural language processing tasks. However, the quadratic computational complexity of the standard attention mechanism poses significant challenges for scaling these models to longer sequences and larger datasets. In this paper, we present \textsc{SparseFormer}, a novel family of sparse attention patterns that achieve linear complexity while maintaining competitive performance with dense attention. Our approach combines local windowed attention with learned global token selection, enabling the model to capture both fine-grained local dependencies and long-range semantic relationships. We conduct extensive experiments on language modeling benchmarks including WikiText-103, The Pile, and a newly curated 500B token corpus. Our results demonstrate that \textsc{SparseFormer} achieves up to 3.2$\times$ speedup in training time and 2.8$\times$ reduction in memory consumption compared to standard Transformers, while maintaining 98.5\% of the perplexity performance on downstream tasks. We also provide theoretical analysis establishing the expressiveness of our sparse attention patterns and prove that they can approximate any continuous sequence-to-sequence function under mild assumptions.
\end{abstract}

\section{Introduction}
\label{sec:intro}

The Transformer architecture \citep{vaswani2017attention} has become the dominant paradigm for natural language processing, achieving state-of-the-art results on tasks ranging from machine translation \citep{wu2016google} to question answering \citep{devlin2019bert,brown2020language}. Central to the Transformer's success is the self-attention mechanism, which allows each token in a sequence to attend to all other tokens, enabling the model to capture complex dependencies regardless of distance.

However, the standard self-attention mechanism has quadratic time and space complexity with respect to sequence length, i.e., $O(n^2)$ for a sequence of length $n$. This quadratic scaling presents significant challenges:

\begin{itemize}
    \item \textbf{Training Cost:} Pre-training large language models requires processing trillions of tokens, and the quadratic attention cost dominates computational budgets.
    \item \textbf{Memory Constraints:} The attention matrix consumes $O(n^2)$ memory, limiting the maximum sequence length that can be processed on modern hardware.
    \item \textbf{Inference Latency:} Real-time applications require fast inference, which is hindered by quadratic complexity for long documents.
\end{itemize}

Numerous approaches have been proposed to address these limitations, including sparse attention patterns \citep{child2019generating,beltagy2020longformer}, low-rank approximations \citep{wang2020linformer,choromanski2021rethinking}, and kernel-based methods \citep{katharopoulos2020transformers}. While these methods successfully reduce computational complexity, they often sacrifice model quality or introduce architectural constraints that limit flexibility.

In this work, we present \textsc{SparseFormer}, a new approach that combines the benefits of sparse attention with learned token selection to achieve both efficiency and effectiveness. Our key contributions are:

\begin{enumerate}
    \item We introduce a novel \textbf{hybrid sparse attention pattern} that combines local windowed attention with dynamically selected global tokens, achieving $O(n \cdot w + n \cdot g)$ complexity where $w$ is the window size and $g$ is the number of global tokens.

    \item We develop a \textbf{differentiable token selection mechanism} based on Gumbel-Softmax that learns which tokens should serve as global connectors during training.

    \item We provide \textbf{theoretical guarantees} showing that our sparse attention pattern is a universal approximator under mild assumptions on the target function class.

    \item We conduct \textbf{comprehensive experiments} demonstrating that \textsc{SparseFormer} achieves competitive performance with dense attention while providing significant speedups.
\end{enumerate}

\section{Related Work}
\label{sec:related}

\subsection{Efficient Transformers}

The quest for efficient Transformers has spawned a rich literature. We categorize existing approaches into several families:

\paragraph{Sparse Attention Patterns.} \citet{child2019generating} introduced Sparse Transformers with fixed strided and local attention patterns. Longformer \citep{beltagy2020longformer} combines local windowed attention with task-specific global attention. BigBird \citep{zaheer2020big} adds random attention to local and global patterns.

\paragraph{Low-Rank Methods.} Linformer \citep{wang2020linformer} projects keys and values to a lower-dimensional space. Performer \citep{choromanski2021rethinking} uses random feature maps to approximate softmax attention.

\paragraph{Recurrence and State Space Models.} Transformer-XL \citep{dai2019transformer} introduces segment-level recurrence. S4 \citep{gu2022efficiently} and Mamba \citep{gu2023mamba} use state space models as alternatives to attention.

\subsection{Token Selection and Pruning}

Dynamic token selection has been explored in various contexts. \citet{goyal2020power} propose adaptive span attention that learns different attention spans for each head. \citet{kim2022learned} introduce learned token pruning for efficient inference.

\section{Method}
\label{sec:method}

\subsection{Preliminaries}

We first review the standard Transformer attention mechanism. Given input embeddings $\mathbf{X} \in \mathbb{R}^{n \times d}$ where $n$ is the sequence length and $d$ is the embedding dimension, self-attention computes:

\begin{equation}
    \text{Attention}(\mathbf{Q}, \mathbf{K}, \mathbf{V}) = \text{softmax}\left(\frac{\mathbf{Q}\mathbf{K}^\top}{\sqrt{d_k}}\right)\mathbf{V}
\end{equation}

where $\mathbf{Q} = \mathbf{X}\mathbf{W}_Q$, $\mathbf{K} = \mathbf{X}\mathbf{W}_K$, and $\mathbf{V} = \mathbf{X}\mathbf{W}_V$ are query, key, and value projections respectively.

\subsection{SparseFormer Architecture}

Our \textsc{SparseFormer} replaces dense attention with a sparse pattern consisting of three components:

\begin{definition}[Local Attention]
For a window size $w$, the local attention mask $\mathbf{M}_\text{local}$ is defined as:
\begin{equation}
    [\mathbf{M}_\text{local}]_{ij} = \begin{cases}
        1 & \text{if } |i - j| \leq w/2 \\
        0 & \text{otherwise}
    \end{cases}
\end{equation}
\end{definition}

\begin{definition}[Global Token Selection]
We learn a selection function $f_\theta: \mathbb{R}^{n \times d} \rightarrow \{0,1\}^n$ that identifies $g$ tokens to serve as global connectors. During training, we use Gumbel-Softmax relaxation:
\begin{equation}
    \mathbf{s} = \text{softmax}\left(\frac{\log \pi + \mathbf{g}}{\tau}\right)
\end{equation}
where $\pi = f_\theta(\mathbf{X})$ are selection logits, $\mathbf{g}$ is Gumbel noise, and $\tau$ is temperature.
\end{definition}

\begin{theorem}[Complexity]
\textsc{SparseFormer} attention has time and space complexity $O(n \cdot (w + g))$ where $w$ is the window size and $g$ is the number of global tokens.
\end{theorem}

\begin{proof}
Each token attends to at most $w$ local tokens and $g$ global tokens. With $n$ tokens, total attention computations are $n \cdot (w + g)$. Since $w$ and $g$ are constants independent of $n$, this is linear in sequence length.
\end{proof}

\subsection{Training Objective}

We train \textsc{SparseFormer} with a combination of language modeling loss and a sparsity regularization term:

\begin{equation}
    \mathcal{L} = \mathcal{L}_\text{LM} + \lambda \cdot \mathcal{L}_\text{sparse}
\end{equation}

\section{Theoretical Analysis}
\label{sec:theory}

\begin{theorem}[Universal Approximation]
\label{thm:universal}
Let $f^*: \mathbb{R}^{n \times d} \rightarrow \mathbb{R}^{n \times d}$ be any continuous function on compact domain. For any $\epsilon > 0$, there exists a \textsc{SparseFormer} model $f_\theta$ with window size $w = O(\log n)$ and $g = O(\log n)$ global tokens such that:
\begin{equation}
    \sup_{\mathbf{X} \in \mathcal{X}} \|f_\theta(\mathbf{X}) - f^*(\mathbf{X})\|_F < \epsilon
\end{equation}
\end{theorem}

\section{Experiments}
\label{sec:experiments}

\subsection{Experimental Setup}

\paragraph{Datasets.} We evaluate on three language modeling benchmarks:
\begin{itemize}
    \item \textbf{WikiText-103} \citep{merity2017pointer}: 103M tokens from Wikipedia
    \item \textbf{The Pile} \citep{gao2020pile}: 825GB diverse text corpus
    \item \textbf{WebText-500B}: Our newly curated 500B token web corpus
\end{itemize}

\paragraph{Baselines.} We compare against: Standard Transformer, Longformer, BigBird, Performer, and Linear Transformer.

\subsection{Main Results}

Table~\ref{tab:main_results} presents our main results on language modeling benchmarks.

\begin{table}[htbp]
\centering
\caption{Perplexity comparison on language modeling benchmarks. Lower is better.}
\label{tab:main_results}
\begin{tabular}{@{}lccc@{}}
\toprule
\textbf{Model} & \textbf{WikiText-103} & \textbf{The Pile} & \textbf{WebText-500B} \\
\midrule
Transformer & 18.3 & 8.42 & 12.1 \\
Longformer & 19.1 & 8.89 & 12.8 \\
BigBird & 18.9 & 8.76 & 12.5 \\
Performer & 21.2 & 9.54 & 14.2 \\
\textsc{SparseFormer} & \textbf{18.5} & \textbf{8.51} & \textbf{12.3} \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Efficiency Analysis}

\begin{table}[htbp]
\centering
\caption{Efficiency comparison for Base models with varying sequence lengths.}
\label{tab:efficiency}
\begin{tabular}{@{}lcccccc@{}}
\toprule
& \multicolumn{3}{c}{\textbf{Throughput (k tok/s)}} & \multicolumn{3}{c}{\textbf{Memory (GB)}} \\
\cmidrule(lr){2-4} \cmidrule(lr){5-7}
\textbf{Model} & 2K & 8K & 32K & 2K & 8K & 32K \\
\midrule
Transformer & 245 & 58 & OOM & 8.2 & 42 & OOM \\
Longformer & 232 & 156 & 42 & 6.1 & 18 & 68 \\
\textsc{SparseFormer} & \textbf{238} & \textbf{185} & \textbf{52} & \textbf{5.8} & \textbf{15} & \textbf{58} \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Ablation Studies}

\paragraph{Effect of Window Size.} Performance improves up to $w=512$, after which gains diminish.

\paragraph{Effect of Global Tokens.} With $g=64$, we achieve 98.5\% of dense attention performance.

\paragraph{Learned vs. Fixed Selection.} Learned token selection outperforms fixed patterns by 0.8 perplexity points.

\section{Discussion}
\label{sec:discussion}

Our results demonstrate that \textsc{SparseFormer} successfully bridges the gap between efficient and effective attention mechanisms.

\paragraph{Scaling Behavior.} The performance gap between \textsc{SparseFormer} and dense attention narrows as model size increases.

\paragraph{Global Token Distribution.} Analysis reveals interpretable patterns: sentence boundaries, rare words, and named entities are frequently selected.

\paragraph{Limitations.} Tasks requiring precise long-range copying may benefit from denser attention patterns.

\section{Conclusion}
\label{sec:conclusion}

We presented \textsc{SparseFormer}, a novel sparse attention mechanism that combines local windowed attention with learned global token selection. Our approach achieves linear complexity while maintaining competitive performance with dense attention.

Future directions include: (1) extending to encoder-decoder architectures, (2) hierarchical selection for very long documents, and (3) combining with quantization and distillation.

\section*{Acknowledgments}

We thank the anonymous reviewers for their valuable feedback. This work was supported by NSF Grant IIS-2023456 and Google Research Scholar Award.

\bibliographystyle{plainnat}
\bibliography{references}

\appendix

\section{Proof of Theorem~\ref{thm:universal}}
\label{app:proof}

\begin{proof}
The proof proceeds in three steps. First, we show that any continuous function can be approximated by a piecewise linear function. Second, we demonstrate that local attention can capture local variations. Third, we prove that $O(\log n)$ global tokens suffice to propagate information across the sequence.
\end{proof}

\section{Implementation Details}
\label{app:implementation}

\begin{table}[htbp]
\centering
\caption{Hyperparameters for model training.}
\label{tab:hyperparams}
\begin{tabular}{@{}lc@{}}
\toprule
\textbf{Hyperparameter} & \textbf{Value} \\
\midrule
Learning rate & 3e-4 \\
Batch size & 256 \\
Warmup steps & 10,000 \\
Total steps & 500,000 \\
Weight decay & 0.1 \\
Window size $w$ & 512 \\
Global tokens $g$ & 64 \\
\bottomrule
\end{tabular}
\end{table}

\section{Additional Results}
\label{app:additional}

\subsection{Per-Domain Analysis}

We analyze performance on different domains within The Pile dataset.

\begin{table}[htbp]
\centering
\caption{Per-domain perplexity on The Pile subsets.}
\begin{tabular}{@{}lcc@{}}
\toprule
\textbf{Domain} & \textbf{Transformer} & \textbf{SparseFormer} \\
\midrule
ArXiv & 6.82 & 6.91 \\
GitHub & 4.21 & 4.28 \\
Wikipedia & 9.15 & 9.24 \\
Books & 12.3 & 12.5 \\
CommonCrawl & 11.8 & 11.9 \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Attention Pattern Visualization}

Figure~\ref{fig:attention} visualizes learned attention patterns across different layers.

\subsection{Computational Cost Breakdown}

The computational cost breakdown shows that attention accounts for 45\% of total FLOPs in standard Transformers, reduced to 18\% in \textsc{SparseFormer}.

\end{document}
"""


def extract_edits(response):
    """Extract edit blocks from response."""
    pattern = r'<<<EDIT>>>\n(.*?)\n<<<ORIGINAL>>>\n(.*?)\n<<<PROPOSED>>>\n(.*?)\n<<<END>>>'
    matches = re.findall(pattern, response, re.DOTALL)
    return [{'desc': m[0].strip(), 'orig': m[1].strip(), 'prop': m[2].strip()} for m in matches]


def apply_edits(doc, edits):
    """Apply edits to document."""
    result = doc
    for e in edits:
        result = result.replace(e['orig'], e['prop'], 1)
    return result


def run_huge_document_test():
    """Test conversion of a large academic paper."""
    print('='*80)
    print('HUGE DOCUMENT TEMPLATE CONVERSION TEST')
    print('='*80)

    # Document statistics
    lines = HUGE_DOC.strip().split('\n')
    chars = len(HUGE_DOC)
    words = len(HUGE_DOC.split())
    sections = HUGE_DOC.count(r'\section{')
    subsections = HUGE_DOC.count(r'\subsection{')
    equations = HUGE_DOC.count(r'\begin{equation}')
    tables = HUGE_DOC.count(r'\begin{table}')
    theorems = HUGE_DOC.count(r'\begin{theorem}') + HUGE_DOC.count(r'\begin{definition}')
    citations = len(re.findall(r'\\cite[pt]?\{', HUGE_DOC))

    print(f'''
📄 DOCUMENT STATISTICS:
   Lines: {len(lines)}
   Characters: {chars:,}
   Words: ~{words:,}
   Sections: {sections}
   Subsections: {subsections}
   Equations: {equations}
   Tables: {tables}
   Theorems/Definitions: {theorems}
   Citations: {citations}
   Authors: 4
''')

    service = SmartAgentServiceV2()
    if not service.client:
        print("⚠️ OpenAI API key not configured")
        return

    results = []

    for template_id in ['acl', 'ieee', 'neurips', 'aaai', 'icml']:
        print('='*80)
        print(f'CONVERTING TO: {CONFERENCE_TEMPLATES[template_id]["name"].upper()}')
        print('='*80)

        service._current_document = HUGE_DOC
        response = ''.join(service._handle_apply_template(template_id))
        edits = extract_edits(response)

        if edits:
            converted = apply_edits(HUGE_DOC, edits)

            print(f'Edits proposed: {len(edits)}')
            for e in edits:
                print(f'  ✓ {e["desc"]}')

            # Verify content preservation
            orig_sections = re.findall(r'\\section\{([^}]+)\}', HUGE_DOC)
            conv_sections = re.findall(r'\\section\{([^}]+)\}', converted)

            orig_equations = HUGE_DOC.count(r'\begin{equation}')
            conv_equations = converted.count(r'\begin{equation}')

            orig_tables = HUGE_DOC.count(r'\begin{table}')
            conv_tables = converted.count(r'\begin{table}')

            orig_theorems = HUGE_DOC.count(r'\begin{theorem}')
            conv_theorems = converted.count(r'\begin{theorem}')

            orig_abstract = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', HUGE_DOC, re.DOTALL)
            conv_abstract = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', converted, re.DOTALL)
            abstract_preserved = orig_abstract and conv_abstract and orig_abstract.group(1).strip() == conv_abstract.group(1).strip()

            print(f'''
📊 CONTENT PRESERVATION CHECK:
   Sections: {len(conv_sections)}/{len(orig_sections)} {"✓" if len(conv_sections) == len(orig_sections) else "⚠️"}
   Equations: {conv_equations}/{orig_equations} {"✓" if conv_equations == orig_equations else "⚠️"}
   Tables: {conv_tables}/{orig_tables} {"✓" if conv_tables == orig_tables else "⚠️"}
   Theorems: {conv_theorems}/{orig_theorems} {"✓" if conv_theorems == orig_theorems else "⚠️"}
   Abstract: {"✓ Preserved" if abstract_preserved else "⚠️ Check manually"}
''')

            # Show new preamble
            preamble_match = re.search(r'^(.*?\\begin\{document\})', converted, re.DOTALL)
            if preamble_match:
                new_preamble = preamble_match.group(1)
                preamble_lines = new_preamble.split('\n')
                print('NEW PREAMBLE (first 25 lines):')
                print('-'*60)
                for i, line in enumerate(preamble_lines[:25], 1):
                    print(f'{i:3d} | {line}')
                if len(preamble_lines) > 25:
                    print(f'    ... ({len(preamble_lines) - 25} more lines)')

            results.append({
                'template': template_id,
                'edits': len(edits),
                'sections_ok': len(conv_sections) == len(orig_sections),
                'equations_ok': conv_equations == orig_equations,
                'tables_ok': conv_tables == orig_tables
            })
            print()
        else:
            print('⚠️ No edits generated')
            results.append({'template': template_id, 'edits': 0, 'sections_ok': False})

    # Final summary
    print('='*80)
    print('CONVERSION SUMMARY')
    print('='*80)
    for r in results:
        status = "✓" if r.get('sections_ok') and r.get('equations_ok') and r.get('tables_ok') else "⚠️"
        print(f"  {status} {r['template'].upper()}: {r['edits']} edits, content preserved: {r.get('sections_ok', False)}")

    print('\n' + '='*80)
    print('✅ HUGE DOCUMENT CONVERSION TEST COMPLETED')
    print('='*80)


if __name__ == "__main__":
    run_huge_document_test()
