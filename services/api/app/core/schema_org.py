"""Shared schema.org vocabulary facts.

Lives in `core` rather than in the scoring or rules modules because both
of those need it and importing either from the other creates a cycle.
"""
from __future__ import annotations

# schema.org subtypes that *are* an Organization for entity purposes, and
# that Google documents as valid organization markup. Matching the literal
# string "Organization" alone under-credits every site that (correctly)
# declares something more specific — a local studio marking itself up as
# ProfessionalService was reading as "no declared entity at all".
ORGANIZATION_TYPES = frozenset({
    "Organization",
    "LocalBusiness",
    "ProfessionalService",
    "Corporation",
    "OnlineBusiness",
    "OnlineStore",
    "NGO",
    "EducationalOrganization",
    "GovernmentOrganization",
    "NewsMediaOrganization",
    "PerformingGroup",
    "SportsOrganization",
    "MedicalOrganization",
    "Airline",
    "Consortium",
    "LibrarySystem",
    "ResearchOrganization",
    "FundingScheme",
    "CooperativeProgram",
})
