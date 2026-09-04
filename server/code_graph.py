import os
import re
from typing import Dict, List, Any, Set

SUPPORTED_EXTENSIONS = {'.cs', '.py', '.ts', '.js', '.tsx', '.jsx'}

# Palavras-chave e tipos genéricos da linguagem a ignorar na indexação de nós
BUILTIN_IGNORE = {
    'List', 'Dictionary', 'HashSet', 'IEnumerable', 'IReadOnlyList', 'IList', 'IDictionary',
    'Task', 'Action', 'Func', 'Type', 'String', 'Color', 'Vector2', 'Vector3', 'Vector4',
    'Matrix', 'Quaternion', 'Math', 'MathF', 'Convert', 'Nullable', 'Exception', 'ArgumentException',
    'Console', 'Debug', 'File', 'Directory', 'Path', 'Stream', 'DateTime', 'TimeSpan', 'Random',
    'int', 'float', 'double', 'bool', 'string', 'void', 'object', 'byte', 'short', 'long',
    'self', 'cls', 'args', 'kwargs', 'init', 'main', 'true', 'false', 'null', 'none',
    'undefined', 'number', 'boolean', 'any', 'never', 'unknown'
}

def extract_file_info(file_path: str) -> Dict[str, Any]:
    """Analisa um arquivo de código e extrai classes, interfaces, funções e importações."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return {}

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return {}

    defined_symbols: Set[str] = set()
    imports_usings: Set[str] = set()
    function_calls: Set[str] = set()

    # Métodos e propriedades públicas
    public_members: List[str] = []

    # C# (.cs)
    namespace_name = ""
    if ext == '.cs':
        # usings: using System.Collections.Generic;
        for m in re.finditer(r'^\s*using\s+([A-Za-z0-9_\.]+);', content, re.MULTILINE):
            imports_usings.add(m.group(1))
        # namespace (usado para clusterização, não para símbolo de nó)
        for m in re.finditer(r'\bnamespace\s+([A-Za-z0-9_\.]+)', content):
            namespace_name = m.group(1)
        # classes, structs, interfaces, enums, records
        for m in re.finditer(r'\b(?:class|interface|struct|enum|record)\s+([A-Za-z0-9_]+)', content):
            sym = m.group(1)
            if len(sym) >= 3 and sym not in BUILTIN_IGNORE:
                defined_symbols.add(sym)
        # Métodos públicos C#: public [async] [static] [override] [virtual] Type Name(...)
        for m in re.finditer(r'^\s*public\s+(?:(?:static|async|override|virtual|abstract|sealed)\s+)*([A-Za-z0-9_<>\[\]]+)\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)', content, re.MULTILINE):
            ret_type, name, params = m.group(1), m.group(2), m.group(3).strip()
            # Ignora construtores simples ou palavras-chave comuns
            if name not in BUILTIN_IGNORE and not name.startswith("get_") and not name.startswith("set_"):
                # Encurta parâmetros para legibilidade
                params_clean = re.sub(r'\s+', ' ', params)
                public_members.append(f"{name}({params_clean}) -> {ret_type}")

    # Python (.py)
    elif ext == '.py':
        # imports: import x, from x import y
        for m in re.finditer(r'^\s*(?:from\s+([A-Za-z0-9_\.]+)\s+import|import\s+([A-Za-z0-9_\.,\s]+))', content, re.MULTILINE):
            imp = m.group(1) or m.group(2)
            if imp:
                imports_usings.add(imp.strip())
        # classes & defs
        for m in re.finditer(r'^\s*class\s+([A-Za-z0-9_]+)', content, re.MULTILINE):
            sym = m.group(1)
            if len(sym) >= 3 and sym not in BUILTIN_IGNORE:
                defined_symbols.add(sym)
        for m in re.finditer(r'^\s*def\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)(?:\s*->\s*([A-Za-z0-9_\[\],\s]+))?:', content, re.MULTILINE):
            name, params, ret = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
            if not name.startswith("__") and name not in BUILTIN_IGNORE:
                ret_str = f" -> {ret}" if ret else ""
                params_clean = re.sub(r'\s+', ' ', params)
                public_members.append(f"{name}({params_clean}){ret_str}")

    # JS / TS (.js, .ts, .jsx, .tsx)
    elif ext in {'.js', '.ts', '.jsx', '.tsx'}:
        # imports: import { x } from './y'
        for m in re.finditer(r'import\s+.*?from\s+[\'"](.*?)[\'"]', content):
            imports_usings.add(m.group(1))
        # classes, interfaces, types, functions
        for m in re.finditer(r'\b(?:export\s+)?(?:class|interface|type)\s+([A-Za-z0-9_]+)', content):
            sym = m.group(1)
            if len(sym) >= 3 and sym not in BUILTIN_IGNORE:
                defined_symbols.add(sym)
        for m in re.finditer(r'\b(?:export\s+)?(?:function|const)\s+([A-Za-z0-9_]+)\s*(?:=\s*(?:async\s*)?\(([^)]*)\)|\(([^)]*)\))', content):
            name = m.group(1)
            params = (m.group(2) or m.group(3) or "").strip()
            if len(name) >= 3 and name not in BUILTIN_IGNORE:
                defined_symbols.add(name)
                public_members.append(f"{name}({params})")

    # Inclui o próprio nome base do arquivo como símbolo de primeira classe
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    if len(base_name) >= 3 and base_name not in BUILTIN_IGNORE:
        defined_symbols.add(base_name)

    return {
        "defined_symbols": sorted(list(defined_symbols)),
        "public_members": public_members[:25],
        "imports": sorted(list(imports_usings)),
        "namespace": namespace_name,
        "lines": content.count('\n') + 1,
        "size_bytes": len(content)
    }

def scan_codebase_graph(root_dir: str, max_files: int = 500) -> Dict[str, Any]:
    """
    Varre o repositório e monta o grafo de dependências e símbolos sem gastar tokens de LLM.
    Utiliza o modelo mental do Obsidian: Symbol Cross-Reference (XRef) onde cada menção
    a uma classe/arquivo atua como um wikilink [[Símbolo]] automático.
    """
    root_dir = os.path.abspath(root_dir)
    files_map: Dict[str, Any] = {}
    symbol_to_files: Dict[str, List[str]] = {}

    ignored_dirs = {'.git', 'bin', 'obj', 'node_modules', '.venv', 'venv', '__pycache__', '.agents', '.gemini', 'dist', 'build', '.idea', '.vscode', 'cockpit-agent', '.cockpit-agent', 'agent-cockpit'}

    count = 0
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith('.')]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in SUPPORTED_EXTENSIONS:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, root_dir).replace('\\', '/')
                info = extract_file_info(full_path)
                if info:
                    files_map[rel_path] = info
                    for sym in info.get("defined_symbols", []):
                        if len(sym) >= 3:
                            symbol_to_files.setdefault(sym, []).append(rel_path)
                    count += 1
                    if count >= max_files:
                        break
        if count >= max_files:
            break

    # Mapeamento de referências cruzadas estilo Obsidian (XRef)
    impact_graph: Dict[str, List[str]] = {}
    valid_symbols = {s: paths for s, paths in symbol_to_files.items() if len(s) >= 3}
    
    if valid_symbols:
        # Compila regex de alta performance combinando todos os símbolos do projeto
        sorted_syms = sorted(valid_symbols.keys(), key=len, reverse=True)
        # Limita a lista de símbolos aos 1500 mais relevantes para máxima velocidade
        pattern_str = r'\b(' + '|'.join(re.escape(s) for s in sorted_syms[:1500]) + r')\b'
        pattern = re.compile(pattern_str)

        for rel_path, info in files_map.items():
            full_path = os.path.join(root_dir, rel_path)
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as fp:
                    file_content = fp.read()
            except Exception:
                continue

            matched_symbols = set(pattern.findall(file_content))
            for sym in matched_symbols:
                target_paths = valid_symbols.get(sym, [])
                for target_path in target_paths:
                    if target_path != rel_path:
                        # rel_path referencia target_path -> target_path impacta rel_path
                        impact_graph.setdefault(target_path, []).append(rel_path)

    return {
        "root_dir": root_dir,
        "scanned_files_count": len(files_map),
        "files": files_map,
        "symbol_index": symbol_to_files,
        "direct_impact_map": impact_graph
    }

def query_impact(root_dir: str, target: str) -> Dict[str, Any]:
    """Determina o raio de impacto de modificar um arquivo ou símbolo específico."""
    graph = scan_codebase_graph(root_dir)
    symbol_index = graph.get("symbol_index", {})
    files_map = graph.get("files", {})

    target_norm = target.replace('\\', '/').strip()
    target_base = os.path.splitext(os.path.basename(target_norm))[0]

    # Encontra arquivos que definem o alvo
    defining_files = symbol_index.get(target, [])
    if not defining_files and target_norm in files_map:
        defining_files = [target_norm]

    # Arquivos que importam ou mencionam o alvo
    dependent_files: Set[str] = set()
    for rel_path, info in files_map.items():
        if rel_path in defining_files:
            continue
        # Checa se o target está nos imports
        for imp in info.get("imports", []):
            if target_base in imp or target in imp:
                dependent_files.add(rel_path)

        # Checa se o target é um símbolo usado no conteúdo
        full_path = os.path.join(root_dir, rel_path)
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                c = f.read()
                if re.search(rf'\b{re.escape(target_base)}\b', c):
                    dependent_files.add(rel_path)
        except Exception:
            pass

    return {
        "target": target,
        "defined_in": defining_files,
        "dependent_files_affected": sorted(list(dependent_files)),
        "total_affected_count": len(dependent_files),
        "impact_risk": "LOW" if len(dependent_files) <= 1 else ("MEDIUM" if len(dependent_files) <= 4 else "HIGH")
    }

def get_graph_elements_for_ui(root_dir: str = ".") -> Dict[str, Any]:
    """Retorna nós e arestas formatados especificamente para renderização visual no dashboard."""
    graph = scan_codebase_graph(root_dir, max_files=400)
    files_map = graph.get("files", {})
    impact_map = graph.get("direct_impact_map", {})

    # Contagem de conexões (grau) de cada arquivo
    node_degrees: Dict[str, int] = {}
    edges = []
    edge_set = set()

    for src, targets in impact_map.items():
        for tgt in targets:
            if src in files_map and tgt in files_map:
                edge_id = f"{src}->{tgt}"
                if edge_id not in edge_set:
                    edge_set.add(edge_id)
                    edges.append({
                        "source": src,
                        "target": tgt
                    })
                    node_degrees[src] = node_degrees.get(src, 0) + 1
                    node_degrees[tgt] = node_degrees.get(tgt, 0) + 1

    nodes = []
    for path, info in files_map.items():
        ext = os.path.splitext(path)[1].lower().replace('.', '')
        # Extrai a pasta principal (ex: Entities, Systems, Tests) para colorização de cluster
        parts = path.split('/')
        cluster = parts[0] if len(parts) > 1 else "Raiz"
        deg = node_degrees.get(path, 0)

        nodes.append({
            "id": path,
            "label": os.path.basename(path),
            "folder": os.path.dirname(path) or "/",
            "cluster": cluster,
            "type": ext,
            "lines": info.get("lines", 0),
            "degree": deg,
            "symbols": info.get("defined_symbols", []),
            "imports": info.get("imports", [])
        })

    # Sincroniza automaticamente o Obsidian Vault em cockpit-agent/vault/
    vault_dir = sync_obsidian_vault(root_dir, files_map, impact_map, node_degrees)

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "vault_path": os.path.relpath(vault_dir, root_dir).replace('\\', '/')
    }

def sync_obsidian_vault(
    root_dir: str,
    files_map: Dict[str, Any],
    impact_map: Dict[str, Set[str]],
    node_degrees: Dict[str, int]
) -> str:
    """
    Gera e mantém sincronizado o Obsidian Vault em {root_dir}/cockpit-agent/vault/.
    Cria arquivos .md com YAML Frontmatter, wikilinks [[...]] e preserva anotações humanas/agentes.
    Garante também a criação da pasta de blueprints em {root_dir}/cockpit-agent/blueprints/.
    """
    root_dir = os.path.abspath(root_dir)
    cockpit_dir = os.path.join(root_dir, "cockpit-agent")
    vault_dir = os.path.join(cockpit_dir, "vault")
    blueprints_dir = os.path.join(cockpit_dir, "blueprints")

    os.makedirs(vault_dir, exist_ok=True)
    os.makedirs(blueprints_dir, exist_ok=True)

    # Configuração básica do Obsidian para reconhecer wikilinks nativos
    obsidian_conf_dir = os.path.join(vault_dir, ".obsidian")
    os.makedirs(obsidian_conf_dir, exist_ok=True)
    app_json = os.path.join(obsidian_conf_dir, "app.json")
    if not os.path.exists(app_json):
        try:
            with open(app_json, "w", encoding="utf-8") as f:
                f.write('{"useMarkdownLinks": false}\n')
        except Exception:
            pass

    clusters_count: Dict[str, int] = {}
    top_hubs: List[Dict[str, Any]] = []

    for file_path, info in files_map.items():
        ext = os.path.splitext(file_path)[1].lower().replace('.', '')
        parts = file_path.split('/')
        cluster = parts[0] if len(parts) > 1 else "Raiz"
        clusters_count[cluster] = clusters_count.get(cluster, 0) + 1

        deg = node_degrees.get(file_path, 0)
        dependents = sorted(list(set(impact_map.get(file_path, []))))
        impact_risk = "LOW" if len(dependents) <= 1 else ("MEDIUM" if len(dependents) <= 4 else "HIGH")
        lines = info.get("lines", 0)

        top_hubs.append({
            "path": file_path,
            "label": os.path.basename(file_path),
            "degree": deg,
            "dependents_count": len(dependents),
            "cluster": cluster
        })

        md_file_path = os.path.join(vault_dir, f"{file_path}.md")
        os.makedirs(os.path.dirname(md_file_path), exist_ok=True)

        existing_notes = ""
        if os.path.exists(md_file_path):
            try:
                with open(md_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                m = re.search(r"<!-- COCKPIT_NOTES_START -->(.*?)<!-- COCKPIT_NOTES_END -->", content, re.DOTALL)
                if m:
                    existing_notes = m.group(1).strip()
            except Exception:
                pass

        if not existing_notes:
            existing_notes = "_Nenhuma anotação adicionada ainda. Registre aqui decisões arquiteturais ou contratos deste arquivo._"

        symbols = sorted(list(set(info.get("defined_symbols", []))))
        symbols_md = "\n".join([f"- `{s}`" for s in symbols]) if symbols else "- _Nenhum símbolo específico exportado_"

        dependents_md = "\n".join([f"- [[{d}.md|{os.path.basename(d)}]]" for d in dependents]) if dependents else "- _Nenhum arquivo dependente direto_"

        imports = sorted(list(set(info.get("imports", []))))
        imports_md = "\n".join([f"- `{imp}`" for imp in imports]) if imports else "- _Nenhum import rastreado_"

        members = info.get("public_members", [])
        members_md = "\n".join([f"- `{m}`" for m in members]) if members else "- _Nenhum método ou membro público detectado_"

        md_content = f"""---
file: {file_path}
cluster: {cluster}
language: {ext}
lines: {lines}
impact_risk: {impact_risk}
degree: {deg}
tags:
  - cluster/{cluster}
  - lang/{ext}
  - risk/{impact_risk.lower()}
---

# {os.path.basename(file_path)}

> 📍 **Caminho:** `{file_path}` | 📏 **Linhas:** {lines} | ⚠️ **Risco de Impacto:** `{impact_risk}` | 🪐 **Cluster:** `{cluster}`

## 🧩 Símbolos Exportados
{symbols_md}

## ⚙️ Métodos Públicos & Assinaturas
{members_md}

## 🔗 Dependências Reversas (Arquivos Afetados por Alterações Aqui)
{dependents_md}

## 📦 Importações & Usings Declarados
{imports_md}

## 📝 Notas & Decisões Arquiteturais (Cockpit Agent)
<!-- COCKPIT_NOTES_START -->
{existing_notes}
<!-- COCKPIT_NOTES_END -->
"""
        try:
            with open(md_file_path, "w", encoding="utf-8") as f:
                f.write(md_content)
        except Exception:
            pass

    # Gera INDEX.md mestre no Vault
    top_hubs.sort(key=lambda x: (x["dependents_count"], x["degree"]), reverse=True)
    hubs_md = "\n".join([f"- [[{h['path']}.md|{h['label']}]] (`{h['cluster']}`) — {h['dependents_count']} dependentes diretos" for h in top_hubs[:15]])
    clusters_md = "\n".join([f"- **{c}**: {cnt} arquivos" for c, cnt in sorted(clusters_count.items(), key=lambda x: x[1], reverse=True)])

    index_path = os.path.join(vault_dir, "INDEX.md")
    index_content = f"""---
tags:
  - cockpit/index
---

# 🛸 Cockpit Agent - Knowledge Graph Index

> **Projeto:** `{os.path.basename(root_dir)}`
> **Total de Arquivos Mapeados:** {len(files_map)}
> **Total de Conexões:** {sum(node_degrees.values()) // 2}
> **Obsidian Vault:** `./cockpit-agent/vault`
> **Master Blueprints:** `./cockpit-agent/blueprints`

---

## 🪐 Módulos / Clusters Arquiteturais
{clusters_md}

---

## ⚡ Top 15 Hubs de Maior Impacto Arquitetural
{hubs_md}
"""
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_content)
    except Exception:
        pass

    return vault_dir

def get_file_vault_note(root_dir: str, file_path: str) -> Dict[str, Any]:
    """Retorna o conteúdo da nota Markdown no vault para o arquivo especificado."""
    root_dir = os.path.abspath(root_dir)
    md_path = os.path.join(root_dir, "cockpit-agent", "vault", f"{file_path}.md")
    if not os.path.exists(md_path):
        return {"found": False, "content": "", "path": md_path}
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(r"<!-- COCKPIT_NOTES_START -->(.*?)<!-- COCKPIT_NOTES_END -->", content, re.DOTALL)
        notes = m.group(1).strip() if m else ""

        return {
            "found": True,
            "full_content": content,
            "notes": notes,
            "path": md_path
        }
    except Exception as e:
        return {"found": False, "content": "", "error": str(e), "path": md_path}

def save_file_vault_note(root_dir: str, file_path: str, notes_content: str) -> Dict[str, Any]:
    """Atualiza a seção de anotações do arquivo no vault preservando o esqueleto."""
    root_dir = os.path.abspath(root_dir)
    md_path = os.path.join(root_dir, "cockpit-agent", "vault", f"{file_path}.md")
    if not os.path.exists(md_path):
        return {"status": "error", "message": f"Nota não encontrada em {md_path}"}
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            existing = f.read()

        start_tag = "<!-- COCKPIT_NOTES_START -->"
        end_tag = "<!-- COCKPIT_NOTES_END -->"
        if start_tag in existing and end_tag in existing:
            prefix = existing.split(start_tag)[0] + start_tag + "\n"
            suffix = "\n" + end_tag + existing.split(end_tag)[1]
            new_full = prefix + notes_content.strip() + suffix
        else:
            new_full = existing + f"\n\n## 📝 Notas & Decisões Arquiteturais (Cockpit Agent)\n{start_tag}\n{notes_content.strip()}\n{end_tag}\n"

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(new_full)
        return {"status": "ok", "path": md_path}
    except Exception as e:
        return {"status": "error", "message": str(e)}
