"""CRC Coding Tutor: free practice for medical coding certification candidates (CRC first).

Not affiliated with or endorsed by AAPC, AHIMA, AMA or CMS. Decision tables and generated
scenarios are drafts until a certified coder reviews them.

Subpackages:
    engine     rules engine, ICD-10-CM lookups, CMS-HCC V28 hierarchy and weights
    rl         student simulator, teaching policies, experiment runner
    generator  scenario generator (local LLM writes the note; the engine decides the answer)
    cms        download CMS files and build the code database
"""

__version__ = "0.1.0"
