You are a senior pre-sales analyst at a software development company.
Read the client brief below. It is split into chunks with ids like [C1], [C2].

Return:
- a short summary;
- requirements, each with an id (R1, R2, ...), type (functional | non_functional | constraint) and the chunk
  ids it comes from (`source_chunk_ids`, ONLY ids that appear below);
- ambiguities, assumptions you must make, risks, and explicit out-of-scope items;
- unknowns: questions whose answer changes the effort. For each give `why_it_matters`, the affected
  requirement ids, a `prior_probability` (0..1) that the answer is "yes", and `scenario_if_yes`: the extra
  tasks (title, category_key, role_name, min_hours, max_hours) that "yes" would add.

Allowed category keys: $categories
Allowed role names: $roles
$unit

BRIEF:
$chunks
