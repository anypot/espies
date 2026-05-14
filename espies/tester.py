import subprocess
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def _detect_languages(repo_dir: Path) -> list[str]:
    """Detect programming languages used in the repository."""
    if not repo_dir.exists():
        logger.warning("Repository does not exist: %s", repo_dir)
        return []

    logger.debug("Detecting languages in %s", repo_dir)

    languages = []

    # Python
    if any(repo_dir.glob("requirements.txt")) or any(repo_dir.glob("pyproject.toml")) or any(repo_dir.glob("setup.py")) or any(repo_dir.glob("Pipfile")):
        languages.append("python")
        logger.debug("Detected Python (manifest files)")

    # JavaScript/Node.js
    if any(repo_dir.glob("package.json")):
        languages.append("javascript")
        logger.debug("Detected JavaScript (package.json)")

    # Rust
    if any(repo_dir.glob("Cargo.toml")):
        languages.append("rust")
        logger.debug("Detected Rust (Cargo.toml)")

    # Go
    if any(repo_dir.glob("go.mod")):
        languages.append("go")
        logger.debug("Detected Go (go.mod)")

    # Java
    if any(repo_dir.glob("pom.xml")) or any(repo_dir.glob("build.gradle")) or any(repo_dir.glob("build.gradle.kts")):
        languages.append("java")
        logger.debug("Detected Java (Maven/Gradle)")

    # Ruby
    if any(repo_dir.glob("Rakefile")) or any(repo_dir.glob("Gemfile")):
        languages.append("ruby")
        logger.debug("Detected Ruby (Rakefile/Gemfile)")

    # Elixir
    if any(repo_dir.glob("mix.exs")):
        languages.append("elixir")
        logger.debug("Detected Elixir (mix.exs)")

    # PHP
    if any(repo_dir.glob("composer.json")):
        languages.append("php")
        logger.debug("Detected PHP (composer.json)")

    # C/C++ (CMake)
    if any(repo_dir.glob("CMakeLists.txt")):
        languages.append("cmake")
        logger.debug("Detected CMake (CMakeLists.txt)")

    # Makefile-based projects
    if any(repo_dir.glob("Makefile")):
        languages.append("make")
        logger.debug("Detected Make (Makefile)")

    logger.info("Detected languages: %s", languages)
    return list(set(languages))


def _run_test_command(cmd: str, cwd: Path) -> tuple[int, str, str]:
    """Run a test command and return (returncode, stdout, stderr)."""
    logger.debug("Running test command: %s (cwd=%s)", cmd, cwd)
    result = subprocess.run(cmd, cwd=cwd, shell=True, text=True, capture_output=True)
    logger.debug("Test command rc=%d, stdout=%d chars, stderr=%d chars", 
                 result.returncode, len(result.stdout), len(result.stderr))
    return result.returncode, result.stdout, result.stderr


def tests(repo_dir: Path) -> tuple[bool, str]:
    """
    Detect languages in the repository and run appropriate test commands.
    Returns (all_passed, combined_output).
    """
    if not repo_dir.exists():
        logger.error("Repository not found: %s", repo_dir)
        return False, "Repository not cloned yet"

    languages = _detect_languages(repo_dir)

    if not languages:
        logger.warning("No recognized programming language found in %s", repo_dir)
        return False, "No recognized programming language found"

    outputs = []
    all_passed = True

    for lang in languages:
        logger.info("Running test suite for: %s", lang.upper())

        if lang == "python":
            rc, out, err = _run_test_command("pytest -q", repo_dir)
            if rc == 0:
                logger.info("Python tests: PASSED")
                outputs.append(f"Python tests: PASSED\n{out}")
            else:
                logger.warning("Python tests: FAILED (rc=%d)", rc)
                outputs.append(f"Python tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "javascript":
            rc, out, err = _run_test_command("npm test", repo_dir)
            if rc == 0:
                logger.info("JavaScript tests: PASSED")
                outputs.append(f"JavaScript tests: PASSED\n{out}")
            else:
                logger.warning("JavaScript tests: FAILED (rc=%d)", rc)
                outputs.append(f"JavaScript tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "rust":
            rc, out, err = _run_test_command("cargo test --quiet", repo_dir)
            if rc == 0:
                logger.info("Rust tests: PASSED")
                outputs.append(f"Rust tests: PASSED\n{out}")
            else:
                logger.warning("Rust tests: FAILED (rc=%d)", rc)
                outputs.append(f"Rust tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "go":
            rc, out, err = _run_test_command("go test ./...", repo_dir)
            if rc == 0:
                logger.info("Go tests: PASSED")
                outputs.append(f"Go tests: PASSED\n{out}")
            else:
                logger.warning("Go tests: FAILED (rc=%d)", rc)
                outputs.append(f"Go tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "java":
            rc, out, err = _run_test_command("mvn test -q", repo_dir)
            if rc != 0:
                logger.debug("Maven failed (rc=%d), trying Gradle", rc)
                rc, out, err = _run_test_command("./gradlew test --no-daemon", repo_dir)
            if rc == 0:
                logger.info("Java tests: PASSED")
                outputs.append(f"Java tests: PASSED\n{out}")
            else:
                logger.warning("Java tests: FAILED (rc=%d)", rc)
                outputs.append(f"Java tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "ruby":
            rc, out, err = _run_test_command("bundle exec rspec", repo_dir)
            if rc == 0:
                logger.info("Ruby tests: PASSED")
                outputs.append(f"Ruby tests: PASSED\n{out}")
            else:
                logger.warning("Ruby tests: FAILED (rc=%d)", rc)
                outputs.append(f"Ruby tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "elixir":
            rc, out, err = _run_test_command("mix test", repo_dir)
            if rc == 0:
                logger.info("Elixir tests: PASSED")
                outputs.append(f"Elixir tests: PASSED\n{out}")
            else:
                logger.warning("Elixir tests: FAILED (rc=%d)", rc)
                outputs.append(f"Elixir tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "php":
            rc, out, err = _run_test_command("phpunit", repo_dir)
            if rc == 0:
                logger.info("PHP tests: PASSED")
                outputs.append(f"PHP tests: PASSED\n{out}")
            else:
                logger.warning("PHP tests: FAILED (rc=%d)", rc)
                outputs.append(f"PHP tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "cmake":
            rc, out, err = _run_test_command("ctest --output-on-failure", repo_dir)
            if rc == 0:
                logger.info("C/C++ tests: PASSED")
                outputs.append(f"C/C++ tests: PASSED\n{out}")
            else:
                logger.warning("C/C++ tests: FAILED (rc=%d)", rc)
                outputs.append(f"C/C++ tests: FAILED\n{out}\n{err}")
                all_passed = False

        elif lang == "make":
            rc, out, err = _run_test_command("make test", repo_dir)
            if rc == 0:
                logger.info("Make tests: PASSED")
                outputs.append(f"Make tests: PASSED\n{out}")
            else:
                logger.warning("Make tests: FAILED (rc=%d)", rc)
                outputs.append(f"Make tests: FAILED\n{out}\n{err}")
                all_passed = False

        else:
            logger.error("No test runner configured for %s", lang)
            outputs.append(f"No test runner configured for {lang}")
            all_passed = False

    combined_output = "\n\n".join(outputs)
    status = "ALL PASSED" if all_passed else "SOME FAILED"
    logger.info("Test run complete: %s", status)
    return all_passed, combined_output
