# Frontend internationalization

PanWatch uses `zh-TW` (繁體中文) as the default for new visitors. A saved
preference always wins. A locale changes only
interface language; it must not implicitly change currency, market, or timezone.

When adding user-facing copy:

1. Put the message in the closest file under `locales/<locale>/` and use a semantic key.
2. Add `zh-TW`, `zh-CN`, and `en-US` text for migrated surfaces.
3. Use `useTranslation` in React components and the helpers in `format.ts` for
   locale-sensitive values.
4. Keep server error text as diagnostic data. New UI behavior must not branch on a
   translated error message.

Chinese is the runtime fallback for missing translation resources.

The `zh-TW` files are generated from `zh-CN` with
`../../scripts/gen-zh-tw.py` (run it from the frontend directory with the project
venv). It converts only string literal values using OpenCC `s2twp`, then applies
the shared Taiwan vocabulary post-processing table. Put deliberate wording
changes in the script's `OVERRIDES` map; do not edit generated files directly.

Run `pnpm check:i18n` to ensure surfaces already declared migrated do not regress by
adding Chinese UI literals. The checker intentionally ignores comments and console
diagnostics; expand its `migratedFiles` list whenever a new page completes migration.
