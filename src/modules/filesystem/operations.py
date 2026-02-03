import os
import shutil
import fnmatch
import aiofiles
from pathlib import Path
from typing import Optional
from src.modules.base import BaseModule
from src.utils.logger import get_logger

logger = get_logger("filesystem")


class FileSystemModule(BaseModule):
    """Filesystem operations module."""
    name = 'filesystem'

    # =========================================================================
    # Directory Operations
    # =========================================================================

    async def list_directory(self, path: str) -> dict:
        """List contents of a directory."""
        logger.debug(f"Listing directory: {path}")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"Path does not exist: {path}")
            if not p.is_dir():
                return self._error(f"Path is not a directory: {path}")

            entries = []
            for entry in p.iterdir():
                try:
                    stat = entry.stat()
                    entries.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if entry.is_file() else None,
                        "modified": stat.st_mtime
                    })
                except (PermissionError, OSError) as e:
                    # Skip entries we can't stat
                    entries.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": None,
                        "error": str(e)
                    })

            return self._success(entries=entries, count=len(entries))
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def create_directory(self, path: str, parents: bool = True) -> dict:
        """
        Create a directory.
        
        Args:
            path: Directory path to create
            parents: If True, create parent directories as needed (default True)
        """
        logger.info(f"Creating directory: {path} (parents={parents})")
        try:
            p = Path(path)
            
            if p.exists():
                if p.is_dir():
                    return self._success(
                        path=str(p),
                        created=False,
                        message="Directory already exists"
                    )
                else:
                    return self._error(f"Path exists but is not a directory: {path}")
            
            p.mkdir(parents=parents, exist_ok=True)
            
            return self._success(
                path=str(p),
                created=True
            )
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def directory_tree(
        self,
        path: str,
        max_depth: int = 5,
        include_files: bool = True,
        include_hidden: bool = False
    ) -> dict:
        """
        Get a recursive tree view of a directory.
        
        Args:
            path: Root directory path
            max_depth: Maximum recursion depth (default 5, max 10)
            include_files: Include files in output (default True)
            include_hidden: Include hidden files/folders (default False)
            
        Returns:
            Nested tree structure with name, type, and children
        """
        logger.debug(f"Building directory tree: {path} (max_depth={max_depth}, include_files={include_files}, include_hidden={include_hidden})")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"Path does not exist: {path}")
            if not p.is_dir():
                return self._error(f"Path is not a directory: {path}")
            
            # Cap max_depth to prevent runaway recursion
            max_depth = min(max_depth, 10)
            
            def build_tree(current_path: Path, depth: int) -> Optional[dict]:
                """Recursively build tree structure."""
                if depth > max_depth:
                    return None
                
                name = current_path.name or str(current_path)
                
                # Skip hidden files/folders if not included
                if not include_hidden and name.startswith('.'):
                    return None
                
                if current_path.is_file():
                    if not include_files:
                        return None
                    try:
                        size = current_path.stat().st_size
                    except (PermissionError, OSError):
                        size = None
                    return {
                        "name": name,
                        "type": "file",
                        "size": size
                    }
                
                elif current_path.is_dir():
                    children = []
                    try:
                        for child in sorted(current_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                            child_node = build_tree(child, depth + 1)
                            if child_node is not None:
                                children.append(child_node)
                    except PermissionError:
                        pass  # Skip directories we can't read
                    
                    return {
                        "name": name,
                        "type": "directory",
                        "children": children
                    }
                
                return None
            
            tree = build_tree(p, 0)
            
            # Count totals
            def count_items(node: dict) -> tuple[int, int]:
                """Returns (file_count, dir_count)"""
                if node["type"] == "file":
                    return (1, 0)
                files, dirs = 0, 1
                for child in node.get("children", []):
                    f, d = count_items(child)
                    files += f
                    dirs += d
                return (files, dirs)
            
            file_count, dir_count = count_items(tree) if tree else (0, 0)
            dir_count -= 1  # Don't count root
            
            return self._success(
                tree=tree,
                file_count=file_count,
                directory_count=dir_count
            )
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def delete_directory(self, path: str, recursive: bool = False) -> dict:
        """Delete a directory. If recursive=True, deletes contents too."""
        logger.warning(f"Deleting directory: {path} (recursive={recursive})")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"Directory does not exist: {path}")
            if not p.is_dir():
                return self._error(f"Path is not a directory: {path}")
            
            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)  # Only works if empty
            
            return self._success(path=str(p), deleted=True)
        except OSError as e:
            if "not empty" in str(e).lower():
                return self._error(f"Directory not empty. Use recursive=True to delete contents.")
            return self._error(str(e))
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    # =========================================================================
    # File Operations
    # =========================================================================

    async def read_file(self, path: str, encoding: str = 'utf-8') -> dict:
        """Read contents of a text file."""
        logger.debug(f"Reading file: {path}")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"File does not exist: {path}")
            if not p.is_file():
                return self._error(f"Path is not a file: {path}")
            
            size = p.stat().st_size
            
            # Limit file size to prevent oversized WebSocket responses (5MB)
            if size > 5 * 1024 * 1024:
                return self._error(
                    f"File too large for WebSocket transfer ({size:,} bytes). "
                    f"Maximum is 5MB. Consider reading specific sections."
                )
            
            async with aiofiles.open(path, 'r', encoding=encoding) as f:
                content = await f.read()
            
            return self._success(
                content=content,
                size=size,
                encoding=encoding
            )
        except UnicodeDecodeError:
            return self._error(f"Cannot read file as text (encoding: {encoding}). File may be binary.")
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def write_file(self, path: str, content: str, encoding: str = 'utf-8', append: bool = False) -> dict:
        """Write content to a file. Creates parent directories if needed.

        Args:
            path: File path to write
            content: Content to write
            encoding: File encoding (default utf-8)
            append: If True, append to file instead of overwriting
        """
        content_size = len(content) if content else 0
        logger.info(f"{'Appending to' if append else 'Writing to'} file: {path} | content_size={content_size} bytes")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)

            mode = 'a' if append else 'w'
            logger.debug(f"Opening file with mode='{mode}', encoding='{encoding}'")

            async with aiofiles.open(path, mode, encoding=encoding) as f:
                await f.write(content)

            size = p.stat().st_size
            logger.info(f"Write complete: {path} | final_size={size} bytes")

            return self._success(path=str(p), bytes_written=size, appended=append)
        except PermissionError:
            logger.error(f"Permission denied writing to: {path}")
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            logger.exception(f"Failed to write file: {path} | error={e}")
            return self._error(str(e))



    async def edit_file(
        self,
        path: str,
        old_text: str,
        new_text: str,
        encoding: str = 'utf-8'
    ) -> dict:
        """
        Edit a file by replacing text. The old_text must appear exactly once in the file.
        
        Args:
            path: File path to edit
            old_text: Text to find and replace (must be unique in file)
            new_text: Replacement text (can be empty to delete)
            encoding: File encoding (default utf-8)
            
        Returns:
            Success with path and replacement info, or error
        """
        logger.info(f"Editing file: {path}")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"File does not exist: {path}")
            if not p.is_file():
                return self._error(f"Path is not a file: {path}")
            
            # Read current content
            async with aiofiles.open(path, 'r', encoding=encoding) as f:
                content = await f.read()
            
            # Count occurrences
            count = content.count(old_text)
            
            if count == 0:
                return self._error(f"Text not found in file. Make sure the text matches exactly, including whitespace.")
            if count > 1:
                return self._error(f"Text appears {count} times in file. It must be unique for safe replacement. Add more context to make it unique.")
            
            # Perform replacement
            new_content = content.replace(old_text, new_text, 1)
            
            # Write back
            async with aiofiles.open(path, 'w', encoding=encoding) as f:
                await f.write(new_content)
            
            return self._success(
                path=str(p),
                old_text_length=len(old_text),
                new_text_length=len(new_text),
                message="File edited successfully"
            )
        except UnicodeDecodeError:
            return self._error(f"Cannot read file as text (encoding: {encoding}). File may be binary.")
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def delete_file(self, path: str) -> dict:
        """Delete a file."""
        logger.warning(f"Deleting file: {path}")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"File does not exist: {path}")
            if not p.is_file():
                return self._error(f"Path is not a file: {path}. Use delete_directory for directories.")
            
            os.remove(path)
            return self._success(path=str(p), deleted=True)
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def copy_file(self, source: str, destination: str) -> dict:
        """
        Copy a file to a new location.
        
        Args:
            source: Source file path
            destination: Destination path (can be file or directory)
            
        If destination is a directory, the file is copied into it with the same name.
        Parent directories are created if needed.
        """
        logger.info(f"Copying file: {source} -> {destination}")
        try:
            src = Path(source)
            dst = Path(destination)
            
            if not src.exists():
                return self._error(f"Source file does not exist: {source}")
            if not src.is_file():
                return self._error(f"Source is not a file: {source}. Use copy_directory for directories.")
            
            # If destination is a directory, copy into it
            if dst.is_dir():
                dst = dst / src.name
            
            # Create parent directories if needed
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            # Perform copy
            shutil.copy2(source, str(dst))  # copy2 preserves metadata
            
            return self._success(
                source=str(src),
                destination=str(dst),
                size=dst.stat().st_size
            )
        except PermissionError:
            return self._error(f"Permission denied")
        except Exception as e:
            return self._error(str(e))



    async def move_file(self, source: str, destination: str) -> dict:
        """
        Move or rename a file or directory.
        
        Args:
            source: Source path
            destination: Destination path
            
        Works for both files and directories.
        If destination is a directory, the source is moved into it.
        Parent directories are created if needed.
        """
        logger.info(f"Moving file: {source} -> {destination}")
        try:
            src = Path(source)
            dst = Path(destination)
            
            if not src.exists():
                return self._error(f"Source does not exist: {source}")
            
            # If destination is an existing directory, move into it
            if dst.is_dir():
                dst = dst / src.name
            
            # Create parent directories if needed
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if destination already exists
            if dst.exists():
                return self._error(f"Destination already exists: {destination}")
            
            # Perform move
            shutil.move(str(src), str(dst))
            
            return self._success(
                source=str(src),
                destination=str(dst),
                is_dir=dst.is_dir()
            )
        except PermissionError:
            return self._error(f"Permission denied")
        except Exception as e:
            return self._error(str(e))

    # =========================================================================
    # Search & Info Operations
    # =========================================================================


    async def search_files(
        self,
        path: str,
        pattern: str,
        max_results: int = 100,
        include_hidden: bool = False
    ) -> dict:
        """
        Search for files matching a pattern.
        
        Args:
            path: Directory to search in
            pattern: Search pattern - supports:
                     - Glob patterns: *.py, **/*.txt, data_*.csv
                     - Simple substring match if no wildcards
            max_results: Maximum results to return (default 100, max 500)
            include_hidden: Include hidden files (default False)
            
        Returns:
            List of matching file paths with basic info
        """
        logger.debug(f"Searching files in: {path} | pattern={pattern} | max_results={max_results} | include_hidden={include_hidden}")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"Path does not exist: {path}")
            if not p.is_dir():
                return self._error(f"Path is not a directory: {path}")
            
            max_results = min(max_results, 500)
            results = []
            
            # Determine if pattern is a glob or simple search
            is_glob = any(c in pattern for c in ['*', '?', '[', ']'])
            
            if is_glob:
                # Use glob pattern
                # If pattern doesn't include path separators, search recursively
                if '/' not in pattern and '\\' not in pattern:
                    # Make it recursive by default for simple patterns like *.py
                    search_pattern = f"**/{pattern}"
                else:
                    search_pattern = pattern
                
                for match in p.glob(search_pattern):
                    if len(results) >= max_results:
                        break
                    
                    # Skip hidden if not included
                    if not include_hidden and any(part.startswith('.') for part in match.parts):
                        continue
                    
                    try:
                        stat = match.stat()
                        results.append({
                            "path": str(match),
                            "name": match.name,
                            "is_dir": match.is_dir(),
                            "size": stat.st_size if match.is_file() else None,
                            "modified": stat.st_mtime
                        })
                    except (PermissionError, OSError):
                        continue
            else:
                # Simple substring search in filenames
                pattern_lower = pattern.lower()
                
                for root, dirs, files in os.walk(path):
                    if len(results) >= max_results:
                        break
                    
                    # Skip hidden directories
                    if not include_hidden:
                        dirs[:] = [d for d in dirs if not d.startswith('.')]
                    
                    for filename in files:
                        if len(results) >= max_results:
                            break
                        
                        if not include_hidden and filename.startswith('.'):
                            continue
                        
                        if pattern_lower in filename.lower():
                            filepath = Path(root) / filename
                            try:
                                stat = filepath.stat()
                                results.append({
                                    "path": str(filepath),
                                    "name": filename,
                                    "is_dir": False,
                                    "size": stat.st_size,
                                    "modified": stat.st_mtime
                                })
                            except (PermissionError, OSError):
                                continue
            
            return self._success(
                matches=results,
                count=len(results),
                truncated=len(results) >= max_results
            )
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))



    async def file_exists(self, path: str) -> dict:
        """Check if a file or directory exists."""
        logger.debug(f"Checking existence: {path}")
        try:
            p = Path(path)
            exists = p.exists()
            is_file = p.is_file() if exists else None
            is_dir = p.is_dir() if exists else None
            
            return self._success(
                path=str(p),
                exists=exists,
                is_file=is_file,
                is_dir=is_dir
            )
        except Exception as e:
            return self._error(str(e))



    async def get_file_info(self, path: str) -> dict:
        """Get detailed info about a file or directory."""
        logger.debug(f"Getting file info: {path}")
        try:
            p = Path(path)
            if not p.exists():
                return self._error(f"Path does not exist: {path}")
            
            stat = p.stat()
            
            return self._success(
                path=str(p),
                name=p.name,
                is_file=p.is_file(),
                is_dir=p.is_dir(),
                size=stat.st_size,
                created=stat.st_ctime,
                modified=stat.st_mtime,
                accessed=stat.st_atime
            )
        except PermissionError:
            return self._error(f"Permission denied: {path}")
        except Exception as e:
            return self._error(str(e))
