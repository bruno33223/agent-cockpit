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
        for m in re.finditer(r'^\s*def\s+([A-Za-z0-9_]+)', content, re.MULTILINE):
            sym = m.group(1)
            if len(sym) >= 3 and sym not in BUILTIN_IGNORE:
                defined_symbols.add(sym)

    # JS / TS (.js, .ts, .jsx, .tsx)
    elif ext in {'.js', '.ts', '.jsx', '.tsx'}:
        # imports: import { x } from './y'
        for m in re.finditer(r'import\s+.*?from\s+[\'"](.*?)[\'"]', content):
            imports_usings.add(m.group(1))
        # classes, interfaces, types, functions
        for m in re.finditer(r'\b(?:class|interface|type)\s+([A-Za-z0-9_]+)', content):
            sym = m.group(1)
            if len(sym) >= 3 and sym not in BUILTIN_IGNORE:
                defined_symbols.add(sym)
        for m in re.finditer(r'\b(?:function|const|let)\s+([A-Za-z0-9_]+)', content):
            sym = m.group(1)
            if len(sym) >= 3 and sym not in BUILTIN_IGNORE:
                defined_symbols.add(sym)

    # Inclui o próprio nome base do arquivo como símbolo de primeira classe
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    if len(base_name) >= 3 and base_name not in BUILTIN_IGNORE:
        defined_symbols.add(base_name)

    return {
        "defined_symbols": sorted(list(defined_symbols)),
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

    ignored_dirs = {'.git', 'bin', 'obj', 'node_modules', '.venv', 'venv', '__pycache__', '.agents', '.gemini', 'dist', 'build', '.idea', '.vscode'}

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

    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": len(nodes),
        "total_edges": len(edges)
    }
