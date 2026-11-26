"""AI xulosa markdown matnini xavfsiz va chiroyli HTML ga o'giruvchi template filtr."""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_CODE_RE = re.compile(r"`([^`]+?)`")
_DECIMAL_RE = re.compile(r"[+-]?\d+\.\d+")


@register.filter(name="int_numbers")
def int_numbers(value: str) -> str:
    """Matndagi kasr sonlarni (masalan 3.000, -2.000) butun son ko'rinishiga o'giradi."""
    if not value:
        return ""

    def _repl(match: re.Match) -> str:
        raw = match.group(0)
        val = round(float(raw))
        return f"{val:+}" if raw.startswith("+") else str(val)

    return _DECIMAL_RE.sub(_repl, str(value))


def _inline_format(text: str) -> str:
    safe = escape(text)
    safe = _BOLD_RE.sub(r'<strong class="font-semibold text-slate-900">\1</strong>', safe)
    safe = _CODE_RE.sub(
        r'<code class="px-1.5 py-0.5 rounded bg-blue-50 text-blue-800 font-mono-num text-xs font-semibold">\1</code>',
        safe,
    )
    return safe


@register.filter(name="render_ai_markdown")
def render_ai_markdown(value: str) -> str:
    if not value:
        return ""

    html_parts: list[str] = []
    in_list = False

    for raw_line in str(value).splitlines():
        line = raw_line.strip()
        if not line:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            continue

        if line.startswith("### ") or line.startswith("## "):
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            title = line.lstrip("#").strip()
            html_parts.append(
                f'<h3 class="text-sm font-bold text-slate-900 mt-3 mb-2 pb-1 border-b border-slate-100">{_inline_format(title)}</h3>'
            )
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_parts.append('<ul class="space-y-2 text-sm text-slate-700">')
                in_list = True
            body = line[2:].strip()
            html_parts.append(
                '<li class="flex items-start gap-2.5 bg-slate-50/80 border border-slate-100 rounded-lg px-3.5 py-2.5">'
                '<span class="mt-1.5 h-2 w-2 rounded-full bg-blue-600 shrink-0" aria-hidden="true"></span>'
                f'<span class="leading-relaxed">{_inline_format(body)}</span>'
                "</li>"
            )
        else:
            if in_list:
                html_parts.append("</ul>")
                in_list = False
            html_parts.append(f'<p class="text-sm text-slate-700 leading-relaxed mb-2">{_inline_format(line)}</p>')

    if in_list:
        html_parts.append("</ul>")

    return mark_safe("\n".join(html_parts))
