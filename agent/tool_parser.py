"""
Módulo de Extracción y Parsing de Llamadas a Herramientas de AETHER IDE.
Permite recuperar llamadas a herramientas emitidas por modelos LLM en JSON,
bloques markdown (diff, json, python) o etiquetas XML.
"""

import ast
import json
import re
from typing import Any, Dict, List, Optional


def extract_tool_calls_from_content(content: str) -> List[Dict[str, Any]]:
    """
    Extrae llamadas a herramientas cuando Ollama/Qwen las devuelve
    embebidas en 'content' (JSON plano o bloques markdown), o sintetiza
    write_file si el modelo devolvió bloques de código pasivos.
    """
    if not content or not content.strip():
        return []

    extracted = []

    # 1. Bloques markdown de herramientas ```json ... ```
    blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    for b in blocks:
        b = b.strip()
        try:
            data = json.loads(b)
            if isinstance(data, dict):
                if "name" in data and "arguments" in data:
                    extracted.append({"function": data})
                elif "function" in data:
                    extracted.append(data)
                elif "plan_steps" in data:
                    extracted.append({"function": {"name": "update_plan", "arguments": data}})
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item and "arguments" in item:
                        extracted.append({"function": item})
        except Exception:
            pass

    # 1.5 Bloques markdown de diff ```diff ... ```
    diff_blocks = re.findall(r"```diff\s*([\s\S]*?)\s*```", content)
    for d in diff_blocks:
        file_m = re.search(r"^\+\+\+\s+(?:b/)?([a-zA-Z0-9_\-\./\\]+)", d, re.MULTILINE)
        if not file_m:
            file_m = re.search(r"^---\s+(?:a/)?([a-zA-Z0-9_\-\./\\]+)", d, re.MULTILINE)
        if file_m:
            d_file = file_m.group(1).split()[0].strip()
            minus_lines = [l[1:] for l in d.splitlines() if l.startswith("-") and not l.startswith("---")]
            plus_lines = [l[1:] for l in d.splitlines() if l.startswith("+") and not l.startswith("+++")]
            if minus_lines and plus_lines:
                extracted.append({
                    "function": {
                        "name": "edit_file",
                        "arguments": {
                            "path": d_file,
                            "target": "\n".join(minus_lines),
                            "replacement": "\n".join(plus_lines)
                        }
                    }
                })

    if extracted:
        return extracted

    # 2. JSON directo en el contenido
    try:
        data = json.loads(content.strip())
        if isinstance(data, dict):
            if "name" in data and "arguments" in data:
                return [{"function": data}]
            elif "function" in data:
                return [data]
            elif "plan_steps" in data:
                return [{"function": {"name": "update_plan", "arguments": data}}]
        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and "name" in item and "arguments" in item:
                    extracted.append({"function": item})
            if extracted:
                return extracted
    except Exception:
        pass

    # 2.2 Fallback con ast.literal_eval para diccionarios con comillas simples de modelos locales
    try:
        val = ast.literal_eval(content.strip())
        if isinstance(val, dict):
            if "name" in val and "arguments" in val:
                return [{"function": val}]
            elif "function" in val:
                return [val]
            elif "plan_steps" in val:
                return [{"function": {"name": "update_plan", "arguments": val}}]
        elif isinstance(val, list):
            for item in val:
                if isinstance(item, dict) and "name" in item and "arguments" in item:
                    extracted.append({"function": item})
            if extracted:
                return extracted
    except Exception:
        pass

    # 3. Escaneo con JSONDecoder para llamadas embebidas
    decoder = json.JSONDecoder()
    pos = 0
    raw = content
    while pos < len(raw):
        idx = raw.find('{', pos)
        if idx == -1:
            break
        try:
            obj, end_pos = decoder.raw_decode(raw[idx:])
            if isinstance(obj, dict):
                if "name" in obj and "arguments" in obj:
                    extracted.append({"function": obj})
                    pos = idx + end_pos
                    continue
                elif "function" in obj and isinstance(obj["function"], dict):
                    extracted.append(obj)
                    pos = idx + end_pos
                    continue
                elif "plan_steps" in obj:
                    extracted.append({"function": {"name": "update_plan", "arguments": obj}})
                    pos = idx + end_pos
                    continue
            pos = idx + 1
        except Exception:
            pos = idx + 1

    if extracted:
        return extracted

    # 4. Rescate resiliente por expresiones regulares para JSON malformado (comillas o escapes inválidos de modelos 7B)
    name_match = re.search(r'"name":\s*"([a-zA-Z0-9_]+)"', content)
    if name_match:
        tool_name = name_match.group(1)
        # Rescate para write_file
        if tool_name == "write_file":
            p_match = re.search(r'"path":\s*"([^"]+)"', content)
            c_match = re.search(r'"content":\s*"(.*)"\s*\}\s*\}', content, re.DOTALL)
            if p_match and c_match:
                raw_content = c_match.group(1)
                clean_content = (
                    raw_content.replace("\\n", "\n")
                    .replace("\\t", "\t")
                    .replace('\\"', '"')
                )
                clean_content = re.sub(r'f""\\+"', 'f"""', clean_content)
                clean_content = re.sub(r'""\\+"', '"""', clean_content)
                clean_content = clean_content.replace('\\\\', '\\')
                return [{
                    "function": {
                        "name": "write_file",
                        "arguments": {
                            "path": p_match.group(1),
                            "content": clean_content
                        }
                    }
                }]

        # Rescate para run_command
        elif tool_name == "run_command":
            cmd_match = re.search(r'"command":\s*"([^"]+)"', content)
            if cmd_match:
                return [{
                    "function": {
                        "name": "run_command",
                        "arguments": {
                            "command": cmd_match.group(1)
                        }
                    }
                }]

        # Rescate para edit_file
        elif tool_name == "edit_file":
            p_match = re.search(r'"path":\s*"([^"]+)"', content)
            t_match = re.search(r'"target":\s*"(.*?)"(?:\s*,\s*"replacement")', content, re.DOTALL)
            r_match = re.search(r'"replacement":\s*"(.*?)"\s*\}\s*\}?', content, re.DOTALL)
            if p_match and t_match and r_match:
                return [{
                    "function": {
                        "name": "edit_file",
                        "arguments": {
                            "path": p_match.group(1),
                            "target": t_match.group(1).replace("\\n", "\n").replace('\\"', '"'),
                            "replacement": r_match.group(1).replace("\\n", "\n").replace('\\"', '"')
                        }
                    }
                }]
            elif p_match and r_match:
                return [{
                    "function": {
                        "name": "write_file",
                        "arguments": {
                            "path": p_match.group(1),
                            "content": r_match.group(1).replace("\\n", "\n").replace('\\"', '"')
                        }
                    }
                }]

    return []
