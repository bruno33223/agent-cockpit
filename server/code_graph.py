import os
import re
from typing import Dict, List, Any, Set

SUPPORTED_EXTENSIONS = {'.cs', '.py', '.ts', '.js', '.tsx', '.jsx'}

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

    # C# (.cs)
    if ext == '.cs':
        # usings: using System.Collections.Generic;
        for m in re.finditer(r'^\s*using\s+([A-Za-z0-9_\.]+);', content, re.MULTILINE):
            imports_usings.add(m.group(1))
        # classes, structs, interfaces, enums
        for m in re.finditer(r'\b(class|interface|struct|enum)\s+([A-Za-z0-9_]+)', content):
            defined_symbols.add(m.group(2))
        # namespace
        for m in re.finditer(r'\bnamespace\s+([A-Za-z0-9_\.]+)', content):
            defined_symbols.add(m.group(1))

    # Python (.py)
    elif ext == '.py':
        # imports: import x, from x import y
        for m in re.finditer(r'^\s*(?:from\s+([A-Za-z0-9_\.]+)\s+import|import\s+([A-Za-z0-9_\.,\s]+))', content, re.MULTILINE):
            imp = m.group(1) or m.group(2)
            if imp:
                imports_usings.add(imp.strip())
        # classes & defs
        for m in re.finditer(r'^\s*class\s+([A-Za-z0-9_]+)', content, re.MULTILINE):
            defined_symbols.add(m.group(1))
        for m in re.finditer(r'^\s*def\s+([A-Za-z0-9_]+)', content, re.MULTILINE):
            defined_symbols.add(m.group(1))

    # JS / TS (.js, .ts, .jsx, .tsx)
    elif ext in {'.js', '.ts', '.jsx', '.tsx'}:
        # imports: import { x } from './y'
        for m in re.finditer(r'import\s+.*?from\s+[\'"](.*?)[\'"]', content):
            imports_usings.add(m.group(1))
        # classes & functions
        for m in re.finditer(r'\b(class|interface|type)\s+([A-Za-z0-9_]+)', content):
            defined_symbols.add(m.group(2))
        for m in re.finditer(r'\bfunction\s+([A-Za-z0-9_]+)', content):
            defined_symbols.add(m.group(1))

    return {
        "defined_symbols": sorted(list(defined_symbols)),
        "imports": sorted(list(imports_usings)),
        "lines": content.count('\n') + 1,
        "size_bytes": len(content)
    }

def scan_codebase_graph(root_dir: str, max_files: int = 150) -> Dict[str, Any]:
    """Varre o repositório e monta o grafo de dependências e símbolos sem gastar tokens de LLM."""
    root_dir = os.path.abspath(root_dir)
    files_map: Dict[str, Any] = {}
    symbol_to_files: Dict[str, List[str]] = {}

    ignored_dirs = {'.git', 'bin', 'obj', 'node_modules', '.venv', 'venv', '__pycache__', '.agents', '.gemini', 'dist', 'build'}

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
                        symbol_to_files.setdefault(sym, []).append(rel_path)
                    count += 1
                    if count >= max_files:
                        break
        if count >= max_files:
            break

    # Calcula referências cruzadas
    impact_graph: Dict[str, List[str]] = {}
    for rel_path, info in files_map.items():
        # Para cada símbolo que este arquivo define, quem o referencia?
        for other_path, other_info in files_map.items():
            if rel_path == other_path:
                continue
            # Se other_path menciona algum símbolo de rel_path
            # Verifica se o nome base do arquivo ou seus símbolos aparecem nos imports
            base_name = os.path.splitext(os.path.basename(rel_path))[0]
            if any(base_name in imp for imp in other_info.get("imports", [])):
                impact_graph.setdefault(rel_path, []).append(other_path)

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
    graph = scan_codebase_graph(root_dir, max_files=100)
    files_map = graph.get("files", {})
    impact_map = graph.get("direct_impact_map", {})

    nodes = []
    edges = []
    edge_set = set()

    for path, info in files_map.items():
        ext = os.path.splitext(path)[1].lower().replace('.', '')
        nodes.append({
            "id": path,
            "label": os.path.basename(path),
            "folder": os.path.dirname(path) or "/",
            "type": ext,
            "lines": info.get("lines", 0),
            "symbols": info.get("defined_symbols", []),
            "imports": info.get("imports", [])
        })

    for src, targets in impact_map.items():
        for tgt in targets:
            if tgt in files_map:
                edge_id = f"{src}->{tgt}"
                if edge_id not in edge_set:
                    edge_set.add(edge_id)
                    edges.append({
                        "source": src,
                        "target": tgt
                    })

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges)
    }
