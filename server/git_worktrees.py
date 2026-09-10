import os
import subprocess
import shutil
from typing import Dict, Any, Optional

def is_inside_worktree(repo_root: str = ".") -> bool:
    """Verifica se já estamos dentro de um worktree vinculado."""
    try:
        git_dir = subprocess.check_output(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.PIPE
        ).strip()
        git_common = subprocess.check_output(
            ["git", "rev-parse", "--git-common-dir"],
            cwd=repo_root,
            text=True,
            stderr=subprocess.PIPE
        ).strip()
        
        # Submodule guard
        submodule = subprocess.run(
            ["git", "rev-parse", "--show-superproject-working-tree"],
            cwd=repo_root,
            capture_output=True,
            text=True
        ).stdout.strip()
        
        if submodule:
            return False
            
        return os.path.abspath(git_dir) != os.path.abspath(git_common)
    except Exception:
        return False

def _rmtree_onerror(func, path, _):
    """Trata arquivos protegidos ou Read-Only no Windows durante a remoção de worktrees."""
    import stat
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except Exception:
        pass

def create_slice_worktree(
    slice_id: str,
    repo_root: str = ".",
    base_branch: Optional[str] = None
) -> Dict[str, Any]:
    """
    Cria uma git worktree isolada em .worktrees/{slice_id} com uma branch dedicada cockpit/{slice_id}.
    Inspirado na diretriz using-git-worktrees do Superpowers.
    """
    repo_root = os.path.abspath(repo_root)
    branch_name = f"cockpit/{slice_id}"
    worktree_dir = os.path.join(repo_root, ".worktrees", slice_id)

    # 1. Se já estiver em worktree, avisa e usa o caminho atual
    if is_inside_worktree(repo_root):
        return {
            "status": "ALREADY_ISOLATED",
            "worktree_path": repo_root,
            "branch": branch_name,
            "message": f"Já em um workspace isolado: {repo_root}"
        }

    # 2. Garante que .worktrees está no .gitignore
    gitignore_path = os.path.join(repo_root, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as f:
            content = f.read()
        if ".worktrees" not in content:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write("\n.worktrees/\n")

    os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)

    # Se o diretório já existir mas não for worktree válido, limpa
    if os.path.exists(worktree_dir):
        # Verifica se git reconhece
        res = subprocess.run(
            ["git", "worktree", "list"],
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        norm_stdout = res.stdout.replace('\\', '/').lower()
        norm_target = worktree_dir.replace('\\', '/').lower()
        if norm_target in norm_stdout:
            return {
                "status": "EXISTS",
                "worktree_path": worktree_dir,
                "branch": branch_name,
                "message": f"Worktree já existente em {worktree_dir}"
            }
        else:
            try:
                shutil.rmtree(worktree_dir, onerror=_rmtree_onerror)
            except Exception:
                pass

    # 3. Executa git worktree add
    cmd = ["git", "worktree", "add", "-B", branch_name, worktree_dir]
    if base_branch:
        cmd.append(base_branch)

    try:
        proc = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        if proc.returncode == 0:
            return {
                "status": "CREATED",
                "worktree_path": worktree_dir,
                "branch": branch_name,
                "message": f"Worktree criada com sucesso em {worktree_dir}"
            }
        else:
            err_msg = proc.stderr.strip()
            # Fallback gracioso se o ambiente não permitir worktree
            return {
                "status": "FALLBACK_LOCAL",
                "worktree_path": repo_root,
                "branch": "HEAD",
                "warning": f"Git worktree falhou ({err_msg}). Usando repositório local diretamente."
            }
    except Exception as e:
        return {
            "status": "FALLBACK_LOCAL",
            "worktree_path": repo_root,
            "branch": "HEAD",
            "warning": f"Exceção ao criar worktree: {str(e)}. Usando repositório local."
        }

def cleanup_slice_worktree(
    slice_id: str,
    repo_root: str = ".",
    delete_branch: bool = True
) -> Dict[str, Any]:
    """Remove a git worktree e opcionalmente a branch associada."""
    repo_root = os.path.abspath(repo_root)
    branch_name = f"cockpit/{slice_id}"
    worktree_dir = os.path.join(repo_root, ".worktrees", slice_id)

    res_log = []

    # 1. Remove worktree via git
    try:
        proc = subprocess.run(
            ["git", "worktree", "remove", "--force", worktree_dir],
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        if proc.returncode == 0:
            res_log.append("Worktree removida do registro do Git.")
        else:
            res_log.append(f"Aviso ao remover worktree: {proc.stderr.strip()}")
    except Exception as e:
        res_log.append(f"Erro ao executar git worktree remove: {str(e)}")

    # 2. Garante exclusão da pasta se sobrou algo
    if os.path.exists(worktree_dir):
        try:
            shutil.rmtree(worktree_dir, onerror=_rmtree_onerror)
            res_log.append("Diretório físico removido.")
        except Exception as e:
            res_log.append(f"Aviso ao deletar diretório: {str(e)}")

    # 3. Executa git worktree prune
    subprocess.run(["git", "worktree", "prune"], cwd=repo_root, capture_output=True)

    # 4. Deleta branch se solicitado
    if delete_branch:
        proc_br = subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=repo_root,
            capture_output=True,
            text=True
        )
        if proc_br.returncode == 0:
            res_log.append(f"Branch '{branch_name}' deletada.")

    return {
        "status": "CLEANED",
        "slice_id": slice_id,
        "details": " | ".join(res_log)
    }
