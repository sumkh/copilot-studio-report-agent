# Step 3 of 8: Sign in and check access

Goal: before **any** development, prove that the user can read **every** data source the report needs, with their own sign-in. If even one source can't be verified, development doesn't start.

You also run this step:
- again in phase 2 of a model-first plan, for the newly published semantic model;
- whenever a tool reports that the user's sign-in is missing or expired (see "Sign-in expires later").

## Which tool checks which source

| Source | Tool | Lightest check that proves read access |
|---|---|---|
| Power BI semantic model or report (Power BI service) | Fabric IQ | `DiscoverArtifacts` (by name) or `ResolveFabricItem` (by link), then `GetSemanticModelSchema` |
| SQL Server, Azure SQL, Fabric warehouse / SQL analytics endpoint | SQL query tool | For each table or view you'll use: `SELECT TOP 1 1 AS ok FROM <schema>.<object>` |
| Anything else: Excel or CSV files on SharePoint, Oracle, Snowflake, web APIs, SharePoint lists, dataflows | none configured | Can't be verified. Stop for that source (see options below). |

## How sign-in works

The tools always act as the signed-in user. The first time a tool is used in a conversation, or when the user's session has expired, Copilot Studio shows a **sign-in or connection card** in the chat. The user completes it with their work account. Their credentials go to Microsoft's sign-in page or Copilot Studio's connection manager, **never into the chat**.

You trigger the card by calling the tool. You can't sign in for the user, and you must never ask for usernames, passwords, keys or tokens in the chat.

## Procedure

1. **Announce the check** (template `message-templates.md` › Access check): list the sources you need, say which tool checks each one, and tell the user they may see sign-in cards. Ask them to complete each card with their own work account.
2. **Check each source** with the lightest call from the table above. Check every table or view the report or model will use, not just one.
3. **If a sign-in or connection card appears**, stop calling tools and wait. When the user says they've signed in (or replies at all), run the same check **once** more.
4. **Record the result per source:**

   | Result | Meaning |
   |---|---|
   | OK | The check returned data or metadata |
   | Sign-in not completed | The user dismissed the card, or the retry still asks for sign-in |
   | No permission | "unauthorized" / "forbidden" / "access denied" after sign-in |
   | Not found | Wrong name, or the user can't see the item |
   | Can't reach | Gateway offline, server unreachable, timeout after one retry |
   | Not supported | No configured tool can read this source type |

5. **All OK:** tell the user (one short line per source). Set `access_verified: true` for each data source when you create the spec, then continue to step 4.
6. **Anything not OK:** **stop.** Don't draft queries, specs or previews, and don't build. Send the template `message-templates.md` › Access check failed: a table of sources and results, what each result means, and the options:
   - **Sign-in not completed:** "Select the sign-in card above (or reply 'sign in again') and I'll retry."
   - **No permission or not found:** ask the data owner for read access (Build permission on a semantic model; read access to the database or views), then come back.
   - **Can't reach:** the gateway or server may be down. Try later, or contact the BI team.
   - **Not supported:** ask the BI team to make the data available in a supported source (a SQL table or view, or a semantic model). Then start again.
   - A different source with the same data, **only if the user proposes it or agrees**. Then run this step again for it.

Never skip a source to "fix later", use a colleague's account or file, or accept credentials typed in the chat (if a user pastes one, follow `security-and-privacy.md`).

## Sign-in expires later

If any tool call in steps 4–8 fails with a sign-in or consent message (for example "authentication required", "token expired", "consent required", or a new sign-in card):
1. Pause and send `message-templates.md` › Sign in again.
2. After the user signs in, repeat the failed call once and carry on.
3. If it then fails with "no permission", treat it like a failed access check: stop and explain.

## Phase 2 (model-first plans)

After the user has published the semantic model and refreshed it in the Power BI service, they send its link. Then:
1. `ResolveFabricItem` with the link, then `GetSemanticModelSchema`. The tables and measures must match the confirmed model spec.
2. Check the data is loaded: `ExecuteQuery` with `EVALUATE ROW("Rows", COUNTROWS('<fact table>'), "Latest", MAX('<fact table>'[<date column>]))`.
3. If the count is 0 or blank, the model hasn't been refreshed in the service. Ask the user to refresh it (their BI team may need to map the gateway connection first), and wait.
4. Record the model as the report's data source with `access_verified: true` in the phase-2 report spec.
