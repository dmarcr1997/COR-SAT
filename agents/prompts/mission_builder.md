# CubeSat Mission Builder

Create one mission candidate.

Required order:

1. Read agents/references/mission_contract.md
2. Read agents/references/sdk_contract.md
3. Write manifest.json
4. Write mission.py
5. Stop

Write both files using write_mission_file.
SDK methods return typed dataclass objects. Use only the fields and attribute-access patterns documented in sdk_contract.md.
Filenames must be exactly:

- manifest.json
- mission.py

Do not include directory paths.

Follow the contracts exactly.
Use only SDK calls documented in sdk_contract.md.
Do not invent methods, properties, or hardware interfaces.
Do not finish until both files are written.

After writing both files, respond:
Mission candidate created.
