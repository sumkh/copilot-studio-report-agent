# Tools for the Report Development Assistant

Audience: the Copilot Studio maker and the tenant admins who approve connections.

The agent needs **three tools**. All of them run **as the signed-in user** (end-user credentials), so the agent can never read or write more than the person chatting with it. When a user first needs a tool, or their session has expired, Copilot Studio shows a **sign-in or connection card** in the chat. The agent triggers it deliberately in its access-check step and waits for the user. Credentials never pass through the chat.

The "no publishing" and "read-only" rules are backed by **not giving the agent any tool that can publish or write**.

**Where to add them.** Add the tools in the Copilot Studio web portal, because creating connections needs the sign-in dialogs there. Then use **Get changes** in the VS Code extension; the tool definitions arrive in the cloned agent under `agent/capabilities/` and connections under `agent/infrastructure/`. Commit them with the rest of `agent/`. The names you give the tools must match `tools` in `org/org-settings.json`.

| Tool | Purpose | Sign-in the user sees |
|---|---|---|
| Fabric IQ (MCP) | Find Power BI reports and semantic models, read schemas, look up values, run read-only DAX; check published models in phase 2 | OAuth sign-in card (Microsoft Entra), once per session |
| SQL query (connector or MCP) | Verify SQL sources, read metadata, test-run queries, check keys, recompute numbers for validation | Connection card (Entra ID, or Windows/SQL auth through a gateway, entered in the connection manager) |
| Save file (OneDrive for Business: Create file) | Save deliverables to the user's own OneDrive | Connection card for OneDrive |

## 1. Fabric IQ MCP server

Microsoft's read-only MCP server for Power BI reports and semantic models. It uses the caller's permissions, including row-level and object-level security; service principals aren't supported. Tools: `DiscoverArtifacts`, `ResolveFabricItem`, `GetReportMetadata`, `GetSemanticModelSchema`, `ValueSearch`, `ExecuteQuery`.

Check first: your tenant's home region must support all Fabric workloads. Fabric IQ isn't available in Power BI-only regions or sovereign clouds. It doesn't read paginated reports, dashboards or apps; users upload .rdl files instead.

**Entra app registration** (single tenant):
1. Entra admin center > App registrations > New registration, with "Accounts in this organizational directory only".
2. API permissions > Add > APIs my organization uses > **Power BI Service** > Delegated: `Item.Read.All`, `Item.Execute.All`.
3. Certificates & secrets: create a client secret (or follow your organisation's credential policy).
4. Add the redirect (callback) URL that Copilot Studio shows in step 6.

**Add it to the agent** (Tools > Add a tool > New tool > Model Context Protocol):
5. Server name `Fabric IQ`. Description: `Read-only access to Power BI reports and semantic models the signed-in user can access: find items, read report metadata and model schemas, search stored values and run DAX queries.` Server URL: `https://fabriciq.svc.cloud.microsoft/v1/mcp/fabriciq` (private links: `https://api.fabric.microsoft.com/v1/mcp/fabriciq`).
6. Authentication: **OAuth 2.0 > Manual**:
   - Client ID and secret from the app registration.
   - Authorization URL: `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/authorize`.
   - Token URL template and Refresh URL: `https://login.microsoftonline.com/<tenant-id>/oauth2/v2.0/token`.
   - Scopes: `https://analysis.windows.net/powerbi/api/Item.Read.All https://analysis.windows.net/powerbi/api/Item.Execute.All offline_access`.
   - Copy the callback URL into the app registration.
7. Create the connection with **end-user authentication**, so each user gets their own sign-in card, and add it to the agent.
8. Recommended: pin the tool contract with the header `X-Variants: Fabric.Routing.FabricIQ.V1` (edit the generated custom connector: Power Apps > Custom connectors > add a "Set HTTP header" policy).
9. In Preview, confirm the six tools are listed and that a sign-in card appears on first use. If tool names differ, update `config/org-config.json` › `tools`.

## 2. SQL query tool (required)

Needed for every SQL source: the access check, metadata, test runs, key checks, building semantic models, and the number checks. Choose one with your data platform team:

| Option | Fits | Notes |
|---|---|---|
| **SQL Server connector**, action *Execute a SQL query (V2)* | Azure SQL, Fabric warehouse / SQL analytics endpoint, with **Microsoft Entra ID** (user) auth; on-premises SQL Server through the **on-premises data gateway** | Each user creates their own connection through the connection card. With Windows/SQL auth via gateway, they type their own database credentials into the **connection manager**, never the chat. Test the gateway path in your tenant. |
| **SQL MCP Server** (Data API builder 1.7+) | Tables and views exposed as read-only entities, hosted in your network with Entra auth | Tighter control over what the agent can see; needs hosting and a network path from Copilot Studio |

Whichever you choose:
- **Read-only at the database:** users reach the data through a read-only role or read-only views. The skill only sends `SELECT`, but the database permission is the real control.
- **End-user credentials:** never a shared or maker-provided connection, or every user would see what that account sees.
- Name the tool in `config/org-config.json` › `tools.sql_query`.
- Grant access to `INFORMATION_SCHEMA` views (metadata checks).

## 3. Save file

**OneDrive for Business > Create file** (directly, or wrapped in an agent flow):
- Connection: **end-user credentials** (each user's own OneDrive).
- Inputs: folder path (`{{OUTPUT_ROOT}}/<file name>`), file name, file content (binary).
- Optional: "Get file metadata" so the agent can return direct links.
- Name the tool in `config/org-config.json` › `tools.save_file`.

Don't add SharePoint or Teams channel upload actions: files filtered by one user's permissions must not land where colleagues can see them.

## Do not add these tools

| Tool | Why not |
|---|---|
| Power BI Authoring MCP (hosted or local) | Writes to semantic models; Microsoft also says not to use it for consumption scenarios. The agent builds model **files** instead, which the user publishes. |
| Power BI or Fabric actions that import, publish, refresh, deploy or change workspaces | Users publish; the agent never acts in Power BI |
| SharePoint / Teams uploads to channels or libraries | Data leakage across permissions |
| Any write-capable database or Fabric tool | Read-only by design |

## Data policies (DLP)

MCP servers in Copilot Studio are governed by Power Platform data policies through their connectors. In the agent's environment, keep Fabric IQ, the SQL tool and OneDrive for Business in the same allowed group, and block connectors that could move data elsewhere. Your admin owns this.
