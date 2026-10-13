# Markdown -> LaTeX section trace

Source: `d137a7d:docs/paper/MANUSCRIPT.md`

| markdown | latex |
| --- | --- |
| `## Abstract` | `\begin{abstract}` |
| `## 1. Introduction` | `\section{...}\label{sec:1}` |
| `## 2. Background` | `\section{...}\label{sec:2}` |
| `### 2.1 Related work` | `\subsection{...}\label{sec:2.1}` |
| `## 3. Methodology` | `\section{...}\label{sec:3}` |
| `### 3.1 Platforms and configurations` | `\subsection{...}\label{sec:3.1}` |
| `### 3.2 Workloads` | `\subsection{...}\label{sec:3.2}` |
| `### 3.3 Metrics and measurement semantics` | `\subsection{...}\label{sec:3.3}` |
| `### 3.4 Compilation and instrumentation paths (three distinct paths)` | `\subsection{...}\label{sec:3.4}` |
| `### 3.5 Measurement-boundary qualification` | `\subsection{...}\label{sec:3.5}` |
| `### 3.6 Cross-platform sensitivity validation design` | `\subsection{...}\label{sec:3.6}` |
| `## 4. Cross-generation simulated characterization (RQ1, RQ2)` | `\section{...}\label{sec:4}` |
| `### 4.1 MAC scaling and saturation (RQ2)` | `\subsection{...}\label{sec:4.1}` |
| `### 4.2 Compiler estimates versus simulated observation` | `\subsection{...}\label{sec:4.2}` |
| `### 4.3 Workload ranking stability` | `\subsection{...}\label{sec:4.3}` |
| `### 4.4 Executability as a result (RQ1 boundary condition)` | `\subsection{...}\label{sec:4.4}` |
| `### 4.5 RQ1 statement` | `\subsection{...}\label{sec:4.5}` |
| `## 5. Validity of the structural metrics across platform and timing conditions` | `\section{...}\label{sec:5}` |
| `## 6. Corstone-320 hardware validation (RQ3)` | `\section{...}\label{sec:6}` |
| `## 7. Operator-level mechanism study: U85 256 → 512 (RQ4)` | `\section{...}\label{sec:7}` |
| `### 7.1 The anomaly and its scope` | `\subsection{...}\label{sec:7.1}` |
| `### 7.2 Instrumentation` | `\subsection{...}\label{sec:7.2}` |
| `### 7.3 The reversal is distributed, not localized` | `\subsection{...}\label{sec:7.3}` |
| `### 7.4 Robustness to memory configuration` | `\subsection{...}\label{sec:7.4}` |
| `### 7.5 Cross-backend instrumentation bridge (U65)` | `\subsection{...}\label{sec:7.5}` |
| `### 7.6 Summary of the mechanism measurements` | `\subsection{...}\label{sec:7.6}` |
| `## 8. Discussion` | `\section{...}\label{sec:8}` |
| `## 9. Limitations` | `\section{...}\label{sec:9}` |
| `### 9.1 Simulation and timing-model validity` | `\subsection{...}\label{sec:9.1}` |
| `### 9.2 Cross-platform and cross-generation comparability` | `\subsection{...}\label{sec:9.2}` |
| `### 9.3 Compiler and instrumentation paths` | `\subsection{...}\label{sec:9.3}` |
| `### 9.4 PMU and runner-output semantic coverage` | `\subsection{...}\label{sec:9.4}` |
| `### 9.5 Causal identifiability` | `\subsection{...}\label{sec:9.5}` |
| `### 9.6 Physical-board scope` | `\subsection{...}\label{sec:9.6}` |
| `## 10. Conclusion` | `\section{...}\label{sec:10}` |
| `## Appendix A` | `\section (appendix A)` |
| `## Appendix B` | `\section (appendix B)` |
