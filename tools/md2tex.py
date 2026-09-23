"""PAPER_v5_20260914.md -> paper_tex/main.tex (IEEEtran journal). Text verbatim; math, tables, figures, cites converted."""
import re, os, sys
ROOT = r'D:\dnld\stm32\hs300v2_foc_ota_001'
md = open(os.path.join(ROOT, 'PAPER_v5_20260914.md'), encoding='utf-8').read()

# ----------------------------------------------------------------- equations (LaTeX bodies)
EQ = {
 1: r'\hat{\omega}_m = \left(K_p + \frac{K_i}{s}\right)\varepsilon',
 2: r'f_{\mathrm{set}}(n+1) = f_{\mathrm{set}}(n) + \Delta f \cdot \mathrm{sgn}\!\left(\Delta P_n \cdot \Delta f_{n-1}\right)',
 3: r'f_{\mathrm{set}} \le 0.11\,V',
 4: r'i_{q,\mathrm{cap}} = \sqrt{i_{\max}^{2} - i_{d,\mathrm{ref}}^{2}}',
 5: r'm = \min\left(0.94,\; 11\,f/V\right)',
 6: r'C\,\frac{dV}{dt} = i_{\mathrm{pv}}(V) - i_L(V,t)',
 7: r'i_{\mathrm{pv}} = I_{\mathrm{sc}}\left[1 - C_1\left(\exp\!\left(\frac{V}{C_2 V_{\mathrm{oc}}}\right) - 1\right)\right]',
 8: r'\begin{aligned} C_2 &= \frac{V_{\mathrm{mp}}/V_{\mathrm{oc}} - 1}{\ln\!\left(1 - I_{\mathrm{mp}}/I_{\mathrm{sc}}\right)},\\ C_1 &= \left(1 - \frac{I_{\mathrm{mp}}}{I_{\mathrm{sc}}}\right)\exp\!\left(-\frac{V_{\mathrm{mp}}}{C_2 V_{\mathrm{oc}}}\right)\end{aligned}',
 9: r'i_L = \frac{P}{V},\qquad \frac{di_L}{dV} = -\frac{P}{V^{2}}',
 10: r'i_L = \frac{V}{R},\qquad \frac{di_L}{dV} = \frac{1}{R}',
 11: r'g(V) + \frac{di_L}{dV} > 0,\quad \text{i.e.}\quad g(V) > \frac{P}{V^{2}}\ \text{for a constant-power load}',
 12: r'\frac{dP}{dV} < L(f),\qquad L(f) = -\frac{S(f)\,c(f)\,P_{\mathrm{hp}}}{300}',
 13: r'\Delta t \approx \frac{C\,\Delta V}{\Delta I_{\mathrm{def}}}',
 14: r'k = \operatorname{clamp}\!\left(\frac{V - \mathrm{LO}\,V_{\mathrm{oc}}}{(\mathrm{HI}-\mathrm{LO})\,V_{\mathrm{oc}}},\, k_{\min},\, 1\right)',
 15: r'\frac{dk_f}{dt} = \frac{k - k_f}{\tau},\qquad \tau = \begin{cases} \tau_a = 2~\mathrm{ms}, & k < k_f\\ \tau_r = 300~\mathrm{ms}, & \text{otherwise}\end{cases}',
 16: r'i_{q,\mathrm{cap}} \leftarrow k_f\, i_{q,\mathrm{cap}}',
 17: r'\begin{aligned} i_L &= \frac{k(V)\,P_0}{V} = \frac{P_0\,(V - V_{\mathrm{LO}})}{(V_{\mathrm{HI}} - V_{\mathrm{LO}})\,V},\\ \frac{di_L}{dV} &= \frac{P_0\,V_{\mathrm{LO}}}{(V_{\mathrm{HI}} - V_{\mathrm{LO}})\,V^{2}} > 0 \end{aligned}',
 18: r'\frac{k_{\min}\,P_0}{V_{\mathrm{LO}}} < i_{\mathrm{pv}}(V_k)\quad \text{and}\quad \frac{P_0}{V_{\mathrm{HI}}} > i_{\mathrm{pv}}(V_{\mathrm{HI}})',
 19: r'V_{\mathrm{uv,trip}} < \mathrm{LO}\,V_{\mathrm{oc}} < \mathrm{HI}\,V_{\mathrm{oc}} < V_{\mathrm{hold,MPPT}} < V_{\mathrm{run,normal}}',
 20: r'd = \operatorname{clamp}\!\left(\frac{\mathrm{HI}\,V_{\mathrm{oc}} - V}{(\mathrm{HI}-\mathrm{LO})\,V_{\mathrm{oc}}},\,0,\,1\right),\qquad f \leftarrow f - d\,R\,T_s',
 21: r'\frac{dP_L}{dV} > 0\ \Rightarrow\ \frac{di_L}{dV} = \frac{1}{V}\frac{dP_L}{dV} - \frac{P_L}{V^{2}} > 0',
 22: r'\Delta W = \int \left(Q_0 - Q(t)\right)\,dt',
 23: r'\eta_y = \frac{\int Q\,dt}{\int P\,dt}',
}

# ----------------------------------------------------------------- inline math tokens (longest first)
TOK = [
 ('C · dv/dt = −(g(V) + di_L/dV) · v', r'C\,dv/dt = -\left(g(V) + di_L/dV\right)v'),
 ('dP_pv/dV = i_pv − V·g(V)', r'dP_{\mathrm{pv}}/dV = i_{\mathrm{pv}} - V\,g(V)'),
 ('0.45·I_rms·√2', r'0.45\,I_{\mathrm{rms}}\sqrt{2}'),
 ('i_q,cap', r'i_{q,\mathrm{cap}}'), ('i_q,ref', r'i_{q,\mathrm{ref}}'), ('i_d,ref', r'i_{d,\mathrm{ref}}'),
 ('i_max', r'i_{\max}'), ('i_pv', r'i_{\mathrm{pv}}'), ('i_L', r'i_L'), ('i_αβ', r'i_{\alpha\beta}'), ('v_αβ', r'v_{\alpha\beta}'),
 ('V_uv,trip', r'V_{\mathrm{uv,trip}}'), ('V_hold,MPPT', r'V_{\mathrm{hold,MPPT}}'), ('V_run,normal', r'V_{\mathrm{run,normal}}'),
 ('V_oc', r'V_{\mathrm{oc}}'), ('V_mp', r'V_{\mathrm{mp}}'), ('V_LO', r'V_{\mathrm{LO}}'), ('V_HI', r'V_{\mathrm{HI}}'), ('V_ref', r'V_{\mathrm{ref}}'), ('V_dc', r'V_{\mathrm{dc}}'),
 ('I_sc', r'I_{\mathrm{sc}}'), ('I_mp', r'I_{\mathrm{mp}}'), ('I_rms', r'I_{\mathrm{rms}}'),
 ('k_min', r'k_{\min}'), ('k_low', r'k_{\mathrm{low}}'), ('k_f', r'k_f'), ('V_k', r'V_k'), ('K_p', r'K_p'), ('K_i', r'K_i'),
 ('ŵ_m', r'\hat{\omega}_m'), ('ŵ_f', r'\hat{\omega}_f'), ('ω_slip', r'\omega_{\mathrm{slip}}'), ('ω_e', r'\omega_e'),
 ('ψ_r,rated', r'\psi_{r,\mathrm{rated}}'), ('ψ_r', r'\psi_r'), ('τ_a', r'\tau_a'), ('τ_r', r'\tau_r'), ('η_y', r'\eta_y'),
 ('ΔI_def', r'\Delta I_{\mathrm{def}}'), ('ΔW', r'\Delta W'), ('ΔV', r'\Delta V'), ('ΔP_n', r'\Delta P_n'), ('Δf', r'\Delta f'), ('Δt', r'\Delta t'),
 ('Q_0', r'Q_0'), ('P_0', r'P_0'), ('P_hp', r'P_{\mathrm{hp}}'), ('P_L', r'P_L'), ('T_s', r'T_s'), ('R_s', r'R_s'), ('L_m', r'L_m'),
 ('f_set', r'f_{\mathrm{set}}'), ('f_min', r'f_{\min}'), ('f_max', r'f_{\max}'), ('S_min', r'S_{\min}'), ('S_max', r'S_{\max}'),
 ('C_1', r'C_1'), ('C_2', r'C_2'), ('i_q', r'i_q'), ('i_d', r'i_d'),
 ('di_L/dV', r'di_L/dV'), ('dP_L/dV', r'dP_L/dV'), ('dP/dV', r'dP/dV'), ('P/V²', r'P/V^{2}'), ('P ∝ V²', r'P \propto V^{2}'),
 ('g(V)', r'g(V)'), ('h(V)', r'h(V)'), ('k(V)', r'k(V)'), ('L(f)', r'L(f)'), ('S(f)', r'S(f)'), ('c(f)', r'c(f)'),
 ('θ', r'\theta'), ('ε', r'\varepsilon'),
]
PH = '\x00%d\x00'

def inline(text):
    """convert a prose string (may contain md bold/italic) to LaTeX"""
    holds = []
    def hold(latex):
        holds.append(latex); return PH % (len(holds) - 1)
    # tokens -> math placeholders
    for k, v in TOK:
        text = text.replace(k, hold('$' + v + '$'))
    # k = 0.21 style, V = 330 V, k < 0.9 etc.
    text = re.sub(r'(?<![\w$])k (=|<|>|≈) ([0-9.]+)', lambda m: hold('$k %s %s$' % ({'=': '=', '<': '<', '>': '>', '≈': r'\approx'}[m.group(1)], m.group(2))), text)
    text = re.sub(r'(?<![\w$])(V|P|C|R|m|d|f) = ([0-9.]+)', lambda m: hold('$%s = %s$' % (m.group(1), m.group(2))), text)
    text = text.replace('V²', hold(r'$V^{2}$')).replace('W/m²', 'W/m' + hold(r'$^{2}$')).replace('m³', 'm' + hold(r'$^{3}$'))
    text = text.replace('kW_p', 'kW' + hold(r'$_{\mathrm{p}}$'))
    # citations
    def cite(m):
        nums = []
        for a, b in re.findall(r'\[(\d+)\](?:-\[(\d+)\])?', m.group(0)):
            a = int(a); b = int(b) if b else a; nums.extend(range(a, b + 1))
        return hold(r'\cite{' + ','.join('r%d' % n for n in nums) + '}')
    text = re.sub(r'\[(\d+)\](?:-\[(\d+)\])?(?:, \[(\d+)\](?:-\[(\d+)\])?)*', cite, text)
    # figure / table / equation references
    def figref(m):
        parts = re.split(r',\s*', m.group(2).strip(' ,'))
        out = []
        for part in parts:
            r = re.split(r'[–\-]', part.strip())
            a = int(r[0]); b = int(r[1]) if len(r) > 1 and r[1] else a
            out.extend(r'\ref{fig:%d}' % n for n in range(a, b + 1))
        return hold(('Fig.~' if len(out) == 1 else 'Figs.~') + ', '.join(out))
    text = re.sub(r'(Figs?)\. ((?:\d+(?:[–\-]\d+)?)(?:, \d+(?:[–\-]\d+)?)*)(?!\d)', figref, text)
    text = re.sub(r'(?<!\w)and Fig\.~', 'and Fig.~', text)
    ROM = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8}
    text = re.sub(r'Table (I{1,3}|IV|VIII|VII|VI|V)\b', lambda m: hold(r'Table~\ref{tab:%d}' % ROM[m.group(1)]), text)
    text = re.sub(r'(?:equation |equations |Equations |condition |the condition )?\((\d{1,2})\)(?:–\((\d{1,2})\))?',
                  lambda m: hold(('(\\ref{eq:%s})' % m.group(1)) + (('--(\\ref{eq:%s})' % m.group(2)) if m.group(2) else '')) if 1 <= int(m.group(1)) <= 23 else m.group(0), text)
    text = re.sub(r'Section ([IVX]+(?:-[A-D])?)', lambda m: hold('Section~' + m.group(1)), text)
    # bold / italic
    text = re.sub(r'\*\*(.+?)\*\*', lambda m: hold(r'\textbf{' + inline_plain(m.group(1)) + '}'), text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)\*(?!\*)', lambda m: hold(r'\emph{' + inline_plain(m.group(1)) + '}'), text)
    text = inline_plain(text)
    # restore placeholders (may nest once)
    for _ in range(3):
        text = re.sub('\x00(\\d+)\x00', lambda m: holds[int(m.group(1))], text)
    return text

def inline_plain(text):
    """character-level conversions for prose outside math"""
    reps = [('×', r'$\times$'), ('≈', r'$\approx$'), ('≤', r'$\le$'), ('≥', r'$\ge$'), ('→', r'$\rightarrow$'), ('←', r'$\leftarrow$'),
            ('−', r'$-$'), ('·', r'$\cdot$'), ('±', r'$\pm$'), ('∝', r'$\propto$'), ('Ω', r'$\Omega$'), ('µ', r'$\mu$'), ('²', r'$^{2}$'), ('³', r'$^{3}$'),
            ('—', '---'), ('–', '--'), ('%', r'\%'), ('&', r'\&'), ('#', r'\#'), ('≥', r'$\ge$'), ('√', r'$\surd$'), ('⁻¹¹', r'$^{-11}$'),
            ('′', r'$^{\prime}$'), ('″', r'$^{\prime\prime}$'), ('~', r'$\sim$'), ('′', "'")]
    # superscript exponents: ⁻⁶, ⁻¹¹ ... -> $^{-6}$, $^{-11}$
    SUP = dict(zip('⁰¹²³⁴⁵⁶⁷⁸⁹', '0123456789'))
    text = re.sub('⁻([⁰¹²³⁴⁵⁶⁷⁸⁹]+)',
                  lambda m: '$^{-' + ''.join(SUP[c] for c in m.group(1)) + '}$', text)
    for a, b in reps:
        text = text.replace(a, b)
    text = re.sub(r'(?<![\\\w])_(?![{])', r'\_', text)
    # number~unit
    text = re.sub(r'(\d)\s(V|A|kW|W|Hz|kHz|ms|s|min|h|m|mF|kWh|Wh|K|baud|dB)\b(?![-\w$])', r'\1~\2', text)
    text = re.sub(r'(\d)\s(\$\\mu\$s|\$\\mu\$F)', r'\1~\2', text)
    text = text.replace('\\%', '\\%')
    text = re.sub(r'(\d)\s\\%', r'\1\\%', text)
    text = text.replace('https://cloud-edge-witness.web.app', r'\url{https://cloud-edge-witness.web.app}')
    return text

# ----------------------------------------------------------------- parse the markdown
lines = md.splitlines()
title = lines[0][2:].strip()
i_abs = md.index('## Abstract'); i_idx = md.index('**Index terms**'); i_intro = md.index('## I. ')
abstract = inline(md[i_abs + len('## Abstract'):i_idx].strip())
keywords = re.search(r'\*\*Index terms\*\* — (.*)', md).group(1).strip().rstrip('.')
i_refs = md.index('## References'); i_figs = md.index('## Figures'); i_data = md.index('## Data Availability')
body = md[i_intro:i_refs]
refs = md[i_refs:i_figs]
figlist = md[i_figs:i_data]
data = md[i_data:]

# figures: number -> (caption, [files])
figs = {}
for m in re.finditer(r'^- Fig\. (\d+)( \(continued\))? — (.*)$', figlist, re.M):
    n = int(m.group(1)); cap = m.group(3)
    files = re.findall(r'`([^`]+\.png)`', cap); cap = re.sub(r' ?\(`[^`]+`\)', '', cap).strip()
    if n in figs:
        figs[n] = (figs[n][0] + ' ' + cap, figs[n][1] + files)
    else:
        figs[n] = (cap, files)
FIGW = {'fig16_setup_composite.png': '0.8\\textwidth', 'fig_steps_5_10kW.png': '0.85\\textwidth', 'fig_ab_B3_A6.png': '0.82\\textwidth'}
WIDE = {'fig01_block.png', 'fig14_E2_vf_vs_vhtd.png', 'fig16_setup_composite.png', 'fig_steps_5_10kW.png', 'fig_ab_B3_A6.png', 'fig16_cloudy_day_20260911.png', 'fig_capture_chain.png'}
def figure_env(n):
    cap, files = figs[n]
    if files and files[0] == 'fig01_block.png':
        return ('\\begin{sidewaysfigure*}[p]\\centering\n\\includegraphics[width=\\textwidth]{../paper_figs/%s}\n\\caption{%s}\\label{fig:%d}\n\\end{sidewaysfigure*}\n'
                % (files[0], inline(cap), n))
    wide = any(f in WIDE for f in files)
    env = 'figure*' if wide else 'figure'
    w = '\\textwidth' if wide else '\\columnwidth'
    if len(files) > 1:
        w = '0.32\\textwidth' if wide else '\\columnwidth'
    if files: w = FIGW.get(files[0], w)
    incs = '\n'.join('\\includegraphics[width=%s]{../paper_figs/%s}' % (w, f) for f in files)
    # A starred float can only be set at the top of a page, so it keeps [!t];
    # a single-column one may also go at the bottom. Top-only placement for
    # every float is what leaves half-empty pages around the tables.
    where = '[!t]' if wide else '[!tbp]'
    return '\\begin{%s}%s\\centering\n%s\n\\caption{%s}\\label{fig:%d}\n\\end{%s}\n' % (env, where, incs, inline(cap), n, env)

# tables
ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8}
WIDE_TABLES = {1, 3, 6, 8}
def table_env(caption_line, rows):
    m = re.match(r'\*\*Table (I{1,3}|IV|VIII|VII|VI|V) —(.*?)\*\*\s*(.*)', caption_line)
    n = ROMAN[m.group(1)]; cap = m.group(2) + ('. ' + m.group(3) if m.group(3) else '')
    cells = [[c.strip() for c in r.strip().strip('|').split('|')] for r in rows if not re.fullmatch(r'\|[-| ]+\|', r.strip())]
    ncol = max(len(r) for r in cells)
    wide = n in WIDE_TABLES
    env = 'table*' if wide else 'table'
    width = '\\textwidth' if wide else '\\columnwidth'
    colspec = 'l' * min(2, ncol) + 'X' * (ncol - min(2, ncol)) if ncol > 3 else 'l' + 'X' * (ncol - 1)
    if n == 4: colspec = 'lXX'
    if n in (1, 8): colspec = '>{\\raggedright\\arraybackslash}p{1.55cm}' + '>{\\raggedright\\arraybackslash}X' * (ncol - 1)
    cap = cap[0].upper() + cap[1:]
    size = 'scriptsize' if (wide or n in (5, 7, 8)) else 'footnotesize'
    tight = '\\setlength{\\tabcolsep}{3pt}\\renewcommand{\\arraystretch}{0.9}' if (wide or n == 5) else ''
    where = '[!t]' if wide else '[!tbp]'
    out = ['\\begin{%s}%s\\caption{%s}\\label{tab:%d}\\centering\\%s%s' % (env, where, inline(cap), n, size, tight),
           '\\begin{tabularx}{%s}{%s}\\toprule' % (width, colspec)]
    for k, r in enumerate(cells):
        r = r + [''] * (ncol - len(r))
        out.append(' & '.join(inline(c) for c in r) + ' \\\\')
        if k == 0: out.append('\\midrule')
    out += ['\\bottomrule\\end{tabularx}\\end{%s}' % env]
    return '\n'.join(out) + '\n'

# body conversion
out = []
cited = set()
paras = re.split(r'\n\n+', body)
k = 0
pending_table_caption = None
while k < len(paras):
    raw = paras[k]; p = raw.strip(); k += 1
    if re.fullmatch(r'-{3,}|—+|\*{3,}', p):
        continue
    if not p: continue
    if re.match(r'^\s{2,}.*\((\d{1,2})\)\s*$', raw):
        n = int(re.search(r'\((\d{1,2})\)\s*$', raw).group(1))
        out.append('\\begin{equation}\n%s\n\\label{eq:%d}\n\\end{equation}' % (EQ[n], n)); continue
    if p.startswith('## '):
        h = re.sub(r'^[IVX]+\. ', '', p[3:]).strip()
        h = re.sub(r' — .*', '', h) if h.startswith('Results') else h
        # IEEE sets the acknowledgment unnumbered, like the data statement
        if h.lower().startswith('acknowledg'):
            out.append('\\section*{%s}' % inline(h)); continue
        out.append('\\section{%s}' % inline(h)); continue
    if p.startswith('### '):
        h = re.sub(r'^[A-E]\. ', '', p[4:]).strip()
        out.append('\\subsection{%s}' % inline(h)); continue
    if '\n1. ' in p:
        lead, rest = p.split('\n1. ', 1)
        items = re.split(r'\n(?=\d+\. )', '1. ' + rest)
        out.append(inline(lead) + '\n\\begin{enumerate}\n' + '\n'.join('\\item ' + inline(re.sub(r'^\d+\. ', '', it)) for it in items) + '\n\\end{enumerate}'); continue
    if p.startswith('**Table '):
        pending_table_caption = p; continue
    if p.startswith('|'):
        out.append(table_env(pending_table_caption, p.splitlines())); pending_table_caption = None; continue
    if re.match(r'^  .*\((\d{1,2})\)\s*$', p):
        n = int(re.search(r'\((\d{1,2})\)\s*$', p).group(1))
        out.append('\\begin{equation}\n%s\n\\label{eq:%d}\n\\end{equation}' % (EQ[n], n)); continue
    if re.match(r'^\d+\. ', p):
        items = re.split(r'\n(?=\d+\. )', p)
        out.append('\\begin{enumerate}\n' + '\n'.join('\\item ' + inline(re.sub(r'^\d+\. ', '', it)) for it in items) + '\n\\end{enumerate}'); continue
    # paragraph, bold lead-in kept as run-in \textbf
    out.append(inline(p))
    # figures first cited in this paragraph
    for m in re.finditer(r'Figs?\. ([\d–\-, ]+)', p):
        for part in re.split(r',\s*', m.group(1).strip(' ,')):
            r = re.split(r'[–\-]', part.strip())
            try:
                a = int(r[0]); b = int(r[1]) if len(r) > 1 and r[1] else a
            except ValueError:
                continue
            for n in range(a, b + 1):
                if n in figs and n not in cited:
                    cited.add(n); out.append(figure_env(n))
for n in sorted(figs):
    if n not in cited: out.append(figure_env(n))

# data availability
data_txt = data[len('## Data Availability'):].strip()
out.append('\\section*{Data Availability}\n' + inline(data_txt))

# bibliography
bib = ['\\begin{thebibliography}{27}']
for m in re.finditer(r'^\[(\d+)\] (.*)$', refs, re.M):
    txt = m.group(2)
    txt = re.sub(r'\*(.+?)\*', r'\\emph{\1}', txt)
    txt = re.sub(r'"(.+?)"', lambda m: '``' + m.group(1) + "''", txt)
    txt = txt.replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('–', '--').replace('—', '---')
    bib.append('\\bibitem{r%s} %s' % (m.group(1), txt))
bib.append('\\end{thebibliography}')

tex = r'''\documentclass[journal]{IEEEtran}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{rotating}
\usepackage{cite}
\usepackage{url}
\usepackage{textcomp}
%% FLOAT PLACEMENT. Without these the wide table*/figure* floats queue up and
%% spill past the bibliography - a starred float can only be set at the top of
%% a page, and the default fractions refuse anything taller than 0.7 of the
%% text height, so one deferral backs up every float behind it.
\usepackage{placeins}
\renewcommand{\topfraction}{0.95}
\renewcommand{\dbltopfraction}{0.95}
\renewcommand{\bottomfraction}{0.9}
\renewcommand{\textfraction}{0.05}
\renewcommand{\floatpagefraction}{0.7}
\renewcommand{\dblfloatpagefraction}{0.7}
\setcounter{topnumber}{3}
\setcounter{dbltopnumber}{3}
\setcounter{bottomnumber}{2}
\setcounter{totalnumber}{5}
\hyphenation{photo-voltaic}
\begin{document}
\title{%s}
\author{Abdulbasit H. Ahmed, Basil M. Saied, and Yasir M. Ameen\thanks{The authors are with the College of Engineering, University of Mosul, Mosul 41001, Iraq. Corresponding author: Abdulbasit H. Ahmed (e-mail: aa.ieee85@gmail.com).}}
\maketitle
\begin{abstract}
%s
\end{abstract}
\begin{IEEEkeywords}
%s
\end{IEEEkeywords}
\IEEEpeerreviewmaketitle
%s
%%%% ONE float barrier, here and nowhere else: floats flow naturally through
%%%% the body, but anything still queued is flushed before the bibliography
%%%% instead of spilling past it. Barriers at every section or subsection
%%%% place the tables more tightly and leave half-empty pages behind them.
\FloatBarrier
%s
\end{document}
''' % (title, abstract, keywords, '\n\n'.join(out), '\n'.join(bib))
os.makedirs(os.path.join(ROOT, 'paper_tex'), exist_ok=True)
open(os.path.join(ROOT, 'paper_tex', 'main.tex'), 'w', encoding='utf-8').write(tex)
print('main.tex written:', len(tex), 'chars; figures', len(figs), 'cited', len(cited), '| bib items', len(bib) - 2)
