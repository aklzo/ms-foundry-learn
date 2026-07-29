"""Core package of the agentic web research tool, ported to Microsoft Agent Framework.

Frontends (CLI) wire together :mod:`config`, the provider factories in
:mod:`llm` / :mod:`search` / :mod:`fetch`, and run the workflow built by
:mod:`workflow`. Progress can be observed via :mod:`events`.

This module intentionally avoids importing ``agent_framework`` so that the
framework-independent parts (knowledge store, SSRF guard, extraction) stay
importable in minimal environments.
"""

__version__ = "0.1.0"
