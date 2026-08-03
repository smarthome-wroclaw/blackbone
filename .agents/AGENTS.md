# Project Rules

## Bilingual Pull Requests

- Write every pull request description in two language versions.
- Put the complete English description first and the complete Polish description second.
- Keep both versions semantically equivalent, including summaries, verification steps, warnings, and notes.
- Clearly separate the versions with `English` and `Polski` headings.
- Keep pull request titles concise and in English unless the user requests otherwise.

## TypeScript Typing

- **Never use `any` type.** Always use proper, specific types or generics.
- fix already existing any usage if you making something in component
- When interfacing with untyped data (e.g., API responses, YAML configs), define explicit interfaces or use `unknown` with type guards.
- Prefer `Record<string, T>` over `{ [key: string]: any }`.
- Use utility types (`Partial<T>`, `Pick<T, K>`, `Omit<T, K>`) to derive types from existing interfaces rather than duplicating or loosening types.
- When migrating existing `any` usage, prioritize files being actively modified.
