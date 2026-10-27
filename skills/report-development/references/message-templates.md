# Message templates

Adapt the wording to the conversation and the user's language; keep the structure. Keep messages short: business users read them in Teams. `<...>` marks things to fill in. For model-first plans, add the phase to the heading, e.g. "Step 4 of 8 (phase 1 of 2: semantic model)".

## Intake (first reply to a report request)

> **Step 1 of 8: Getting your samples**
> Happy to help build this report. Before I design anything, I'd like to see what you use today, so the new report uses the right data and looks like what you're used to. Please share whatever you have:
> 1. **Your current Excel report** (.xlsx). A recent final version is best. Which period and filters is it for?
> 2. **The paginated report** behind it, if there is one (.rdl file).
> 3. **The Power BI report** it comes from: the link from your browser, or the file.
> 4. Anything that should be different in the new version.
>
> Later I'll ask you to **sign in to each data source with your own account**. I only start building once I've confirmed you can access all the data. I don't publish anything: you'll get files to review and publish yourself.

## Analysis summary (end of step 2)

> **Step 2 of 8: What I found in your samples**
> **Data:** <SQL database SalesDW on sql-prod-01> (found in <your paginated report's data source>).
> **Your columns and where they come from:**
> | Your column | Source | Status |
> |---|---|---|
> | Region | DimRegion.RegionName | confirmed |
> | Margin % | calculated: (Sales − Cost) / Sales | from your Excel formula |
> **Suggested approach:** <build a semantic model first, then the paginated report on it, because <reason>> | <build the report directly on <source>>. OK with you?
> **Layout I'll copy:** <grouped by Region with subtotals and a grand total; A4 landscape; dark blue header>.
> **Can't be copied exactly:** <Excel formulas become values; frozen panes>.
> **Questions:** <max 3, numbered>

## Access check (start of step 3)

> **Step 3 of 8: Signing in and checking access**
> Before I build anything, I'll check you can read all the data this report needs:
> - <SalesDW on sql-prod-01>: SQL tool
> - <Sales Analytics Model>: Power BI (Fabric IQ)
>
> You may see **sign-in cards** in this chat. Please complete each one with your own work account. Never type passwords into the chat.

## Sign-in card shown

> Please complete the sign-in card above with your work account, then reply **done** and I'll continue.

## Access check passed

> ✅ Access confirmed: <source 1>, <source 2>. Next I'll write the query and test it with your sample's period.

## Access check failed (development doesn't start)

> I can't start building yet because I couldn't confirm access to all the data:
> | Data source | Result | What it means |
> |---|---|---|
> | <SalesDW> | <No permission> | <Your account can't read FactSales> |
> **Options:**
> 1. <Ask the data owner (<owner if known>) for read access, then tell me and I'll check again.>
> 2. <Select the sign-in card again (reply "sign in again").>
> 3. <Use another source you can access that has the same data.>
> 4. <Pass this to the BI team (<bi_team_contact>); I can summarise what we've worked out.>

## Sign in again (session expired mid-conversation)

> Your sign-in to <source> has expired. Please complete the sign-in card above (or reply "sign in again"), then reply **done** and I'll pick up where we left off.

## Gate A (step 4)

> **Step 4 of 8: Please confirm the data**
> I ran the query for **<period of your sample>**: <N rows><, and the totals match your sample>.
> <spec_tool summary --gate data>
> Reply **CONFIRM DATA** if this is right, or tell me what to change.

## Gate B (step 5)

> **Step 5 of 8: Please confirm the <report design | model design>**
> Attached is a **<layout preview | wireframe | model diagram>** so you can see what you'll get.
> <spec_tool summary --gate spec>
> Reply **CONFIRM SPEC** if this is what you want, or tell me what to change.

## Build done (step 6)

> **Step 6 of 8: <Report | Semantic model> built**
> I've built **<file name>**: <one-line summary>. The structure check passed. Now I'm checking the numbers against your sample.

## Validation result (step 7)

> **Step 7 of 8: Number check**: <✅ all numbers match your sample | ⚠️ N differences found>
> | Measure | Your sample | New <report/model> | Difference |
> |---|---|---|---|
> | Sales Amount | 2,363,100.00 | 2,364,350.00 | +1,250.00 |
> <For differences: up to 5 examples, the likely cause, and what you suggest. Ask whether to accept them or what to change.>
> Details are in **<reconciliation file>**.

## Handover (step 8, report)

> **Step 8 of 8: Your files are ready**
> **Saved to:** <link(s)>
> - `<file_name>_v<N>.rdl`: the report
> - `<file_name>_spec_v<N>.json`: the confirmed design (upload it if you want changes later)
> - `<file_name>_reconciliation_v<N>.xlsx`: the number check
>
> **Test it (no publishing needed):** <2–3 steps from 08-handoff.md, including signing in to the data when asked>. Use **<sample parameters>** and send me the exported Excel file. I'll compare it with your sample, including formatting.
> **Publish when you're happy:** <2–3 steps>. <Data source connection note.>
> **Good to know:** <expected differences>.

## Model handover (step 8, phase 1)

> **Step 8 of 8 (phase 1 of 2): Your semantic model is ready**
> **Saved to:** <link(s)>: `<file_name>_v<N>_pbip.zip` (model + a "Model check" page), the spec and the SQL number check.
> **Next steps for you:**
> 1. Unzip and open `<file_name>.pbip` in Power BI Desktop. Select **Refresh** and **sign in to <server>** with your own account when asked.
> 2. Check the **Model check** page against your sample (the numbers matched in my SQL check: <summary>).
> 3. **Publish** it to <workspace>. Your BI team sets up the gateway connection and scheduled refresh.
> 4. Send me the **link to the published model**, and I'll build the <paginated report> on it (phase 2).

## Phase 2 start (user sends the model link)

> Thanks! **Step 3 of 8 (phase 2 of 2): Checking the published model**
> I'll confirm you can access <model> and that it has been refreshed with data.

## Round-trip request

> Could you run the <report | model> for **<sample period/filters>**, export it to Excel and upload the file here? I'll compare it with your original, including numbers and formatting. You'll be asked to sign in to the data when it first runs. You don't need to publish to a shared workspace: <Report Builder: Run, then Export > Excel | My workspace | Desktop: Refresh>.

## Out of scope

> That's outside what I can do here: <publishing / row-level security / ...>. <bi_team_contact> can help. I can prepare a summary of what we've worked out so far to send them.

## Restricted file

> This file is labelled **<label>**, which I'm not allowed to process. Please contact <bi_team_contact> for help with reports on this data.

## Change request after confirmation

> Here's what changes: <diff in plain words>. This affects the <data | design> you confirmed earlier. Reply **CONFIRM <DATA|SPEC>** to approve the updated version (v<N>).
