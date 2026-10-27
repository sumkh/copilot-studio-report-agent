"""Synthetic Power BI / paginated fixtures (fictional Contoso data) used by make_fixtures.py."""
import json
import uuid
import zipfile

MODEL_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/"


def _tb(name, value, style="", para_style="", box_style=""):
    return ('<Textbox Name="%s"><CanGrow>true</CanGrow><KeepTogether>true</KeepTogether><Paragraphs><Paragraph>'
            '<TextRuns><TextRun><Value>%s</Value><Style>%s</Style></TextRun></TextRuns><Style>%s</Style>'
            '</Paragraph></Paragraphs><rd:DefaultName>%s</rd:DefaultName><Style>%s<PaddingLeft>2pt</PaddingLeft>'
            '<PaddingRight>2pt</PaddingRight><PaddingTop>2pt</PaddingTop><PaddingBottom>2pt</PaddingBottom></Style></Textbox>'
            % (name, value, style, para_style, name, box_style))


HDR = "<FontFamily>Calibri</FontFamily><FontSize>10pt</FontSize><FontWeight>Bold</FontWeight><Color>White</Color>"
HDR_BOX = "<Border><Color>#BFBFBF</Color><Style>Solid</Style></Border><BackgroundColor>#1F4E78</BackgroundColor><VerticalAlign>Middle</VerticalAlign>"
DET = "<FontFamily>Calibri</FontFamily><FontSize>10pt</FontSize>"
DET_BOX = "<Border><Color>#D9D9D9</Color><Style>Solid</Style></Border>"
SUB = "<FontFamily>Calibri</FontFamily><FontSize>10pt</FontSize><FontWeight>Bold</FontWeight>"
SUB_BOX = "<Border><Color>#D9D9D9</Color><Style>Solid</Style></Border><BackgroundColor>#DDEBF7</BackgroundColor>"
TOT_BOX = "<Border><Color>#D9D9D9</Color><Style>Solid</Style></Border><BackgroundColor>#BDD7EE</BackgroundColor>"


def _cell(tb):
    return "<TablixCell><CellContents>%s</CellContents></TablixCell>" % tb


def build_rdl_sample(path):
    cols = [("ProductCategory", "Product Category", None, "Left", 1.6),
            ("Units", "Units", "#,##0", "Right", 0.9),
            ("SalesAmount", "Sales Amount", "#,##0.00", "Right", 1.2),
            ("Cost", "Cost", "#,##0.00", "Right", 1.2),
            ("MarginPct", "Margin %", "0.0%", "Right", 0.9)]
    header = "".join(_cell(_tb("hdr_" + f, h, HDR, "<TextAlign>Center</TextAlign>", HDR_BOX)) for f, h, _, _, _ in cols)
    detail = "".join(_cell(_tb("det_" + f, "=Fields!%s.Value" % f, DET + ("<Format>%s</Format>" % fmt if fmt else ""),
                               "<TextAlign>%s</TextAlign>" % al, DET_BOX)) for f, h, fmt, al, _ in cols)

    def agg(f, fmt, prefix, box):
        if f == "ProductCategory":
            return _tb(prefix + f, "", SUB, "", box)
        if f == "MarginPct":
            v = "=IIf(Sum(Fields!SalesAmount.Value) = 0, 0, (Sum(Fields!SalesAmount.Value) - Sum(Fields!Cost.Value)) / Sum(Fields!SalesAmount.Value))"
        else:
            v = "=Sum(Fields!%s.Value)" % f
        return _tb(prefix + f, v, SUB + "<Format>%s</Format>" % fmt, "<TextAlign>Right</TextAlign>", box)
    sub = "".join(_cell(agg(f, fmt, "sub_", SUB_BOX)) for f, h, fmt, al, _ in cols)
    tot = "".join(_cell(agg(f, fmt, "tot_", TOT_BOX)) for f, h, fmt, al, _ in cols)
    widths = "".join("<TablixColumn><Width>%sin</Width></TablixColumn>" % w for *_, w in cols)
    row = lambda cells: "<TablixRow><Height>0.25in</Height><TablixCells>%s</TablixCells></TablixRow>" % cells
    rh = lambda name, value, style, box: ("<TablixHeader><Size>1.2in</Size><CellContents>%s</CellContents></TablixHeader>"
                                         % _tb(name, value, style, "", box))
    tablix = (
        '<Tablix Name="tblSales"><TablixBody><TablixColumns>%s</TablixColumns><TablixRows>%s%s%s%s</TablixRows></TablixBody>'
        '<TablixColumnHierarchy><TablixMembers>%s</TablixMembers></TablixColumnHierarchy>'
        '<TablixRowHierarchy><TablixMembers>'
        '<TablixMember>%s<KeepWithGroup>After</KeepWithGroup><RepeatOnNewPage>true</RepeatOnNewPage></TablixMember>'
        '<TablixMember><Group Name="grpRegion"><GroupExpressions><GroupExpression>=Fields!Region.Value</GroupExpression></GroupExpressions></Group>'
        '<SortExpressions><SortExpression><Value>=Fields!Region.Value</Value></SortExpression></SortExpressions>%s'
        '<TablixMembers><TablixMember><Group Name="Details" /><SortExpressions><SortExpression><Value>=Fields!ProductCategory.Value</Value></SortExpression></SortExpressions></TablixMember>'
        '<TablixMember><KeepWithGroup>Before</KeepWithGroup></TablixMember></TablixMembers></TablixMember>'
        '<TablixMember>%s<KeepWithGroup>Before</KeepWithGroup></TablixMember>'
        '</TablixMembers></TablixRowHierarchy>'
        '<RepeatColumnHeaders>true</RepeatColumnHeaders><DataSetName>dsSales</DataSetName>'
        '<Top>0in</Top><Left>0in</Left><Height>1in</Height><Width>7in</Width><Style><Border><Style>None</Style></Border></Style></Tablix>'
    ) % (widths, row(header), row(detail), row(sub), row(tot),
         "<TablixMember />" * len(cols),
         rh("hdr_Region", "Region", HDR, HDR_BOX),
         rh("grp_Region", "=Fields!Region.Value", SUB, SUB_BOX),
         rh("tot_Region", "Grand Total", SUB, TOT_BOX))
    title = ('<Textbox Name="txtTitle"><CanGrow>true</CanGrow><KeepTogether>true</KeepTogether><Paragraphs><Paragraph><TextRuns>'
             '<TextRun><Value>Sales by Region</Value><Style><FontFamily>Calibri</FontFamily><FontSize>14pt</FontSize><FontWeight>Bold</FontWeight><Color>#1F4E78</Color></Style></TextRun>'
             '</TextRuns><Style /></Paragraph><Paragraph><TextRuns><TextRun><Value>="Period: " &amp; Format(Parameters!StartDate.Value, "dd MMM yyyy") &amp; " - " &amp; Format(Parameters!EndDate.Value, "dd MMM yyyy")</Value>'
             '<Style><FontFamily>Calibri</FontFamily><FontSize>10pt</FontSize><FontStyle>Italic</FontStyle><Color>#595959</Color></Style></TextRun></TextRuns><Style /></Paragraph></Paragraphs>'
             '<Top>0in</Top><Left>0in</Left><Height>0.5in</Height><Width>7in</Width><Style><Border><Style>None</Style></Border></Style></Textbox>')
    footer = ('<Textbox Name="txtPage"><CanGrow>true</CanGrow><KeepTogether>true</KeepTogether><Paragraphs><Paragraph><TextRuns>'
              '<TextRun><Value>="Page " &amp; Globals!PageNumber &amp; " of " &amp; Globals!TotalPages</Value><Style><FontFamily>Calibri</FontFamily><FontSize>8pt</FontSize></Style></TextRun>'
              '</TextRuns><Style><TextAlign>Center</TextAlign></Style></Paragraph></Paragraphs><Top>0in</Top><Left>0in</Left><Height>0.25in</Height><Width>7in</Width><Style /></Textbox>')
    rdl = '''<?xml version="1.0" encoding="utf-8"?>
<Report xmlns="http://schemas.microsoft.com/sqlserver/reporting/2016/01/reportdefinition" xmlns:rd="http://schemas.microsoft.com/SQLServer/reporting/reportdesigner">
  <Description>Monthly sales by region and product category</Description>
  <Author>Finance Reporting</Author>
  <AutoRefresh>0</AutoRefresh>
  <DataSources>
    <DataSource Name="SalesDW">
      <ConnectionProperties>
        <DataProvider>SQL</DataProvider>
        <ConnectString>Data Source=sql-prod-01.contoso.local;Initial Catalog=SalesDW</ConnectString>
        <IntegratedSecurity>true</IntegratedSecurity>
      </ConnectionProperties>
      <rd:SecurityType>Integrated</rd:SecurityType>
      <rd:DataSourceID>%(ds1)s</rd:DataSourceID>
    </DataSource>
    <DataSource Name="FinanceShared">
      <DataSourceReference>/Data Sources/FinanceDW</DataSourceReference>
      <rd:SecurityType>None</rd:SecurityType>
      <rd:DataSourceID>%(ds2)s</rd:DataSourceID>
    </DataSource>
  </DataSources>
  <DataSets>
    <DataSet Name="dsSales">
      <Query>
        <DataSourceName>SalesDW</DataSourceName>
        <QueryParameters>
          <QueryParameter Name="@StartDate"><Value>=Parameters!StartDate.Value</Value></QueryParameter>
          <QueryParameter Name="@EndDate"><Value>=Parameters!EndDate.Value</Value></QueryParameter>
          <QueryParameter Name="@Region"><Value>=Parameters!Region.Value</Value></QueryParameter>
        </QueryParameters>
        <CommandText>SELECT r.RegionName AS Region, p.Category AS ProductCategory,
       SUM(f.Units) AS Units, SUM(f.SalesAmount) AS SalesAmount, SUM(f.Cost) AS Cost
FROM dbo.FactSales f
JOIN dbo.DimRegion r ON r.RegionKey = f.RegionKey
JOIN dbo.DimProduct p ON p.ProductKey = f.ProductKey
JOIN dbo.DimDate d ON d.DateKey = f.DateKey
WHERE d.[Date] BETWEEN @StartDate AND @EndDate
  AND r.RegionName IN (@Region)
GROUP BY r.RegionName, p.Category</CommandText>
        <rd:UseGenericDesigner>true</rd:UseGenericDesigner>
      </Query>
      <Fields>
        <Field Name="Region"><DataField>Region</DataField><rd:TypeName>System.String</rd:TypeName></Field>
        <Field Name="ProductCategory"><DataField>ProductCategory</DataField><rd:TypeName>System.String</rd:TypeName></Field>
        <Field Name="Units"><DataField>Units</DataField><rd:TypeName>System.Int32</rd:TypeName></Field>
        <Field Name="SalesAmount"><DataField>SalesAmount</DataField><rd:TypeName>System.Decimal</rd:TypeName></Field>
        <Field Name="Cost"><DataField>Cost</DataField><rd:TypeName>System.Decimal</rd:TypeName></Field>
        <Field Name="MarginPct"><Value>=IIf(Fields!SalesAmount.Value = 0, 0, (Fields!SalesAmount.Value - Fields!Cost.Value) / Fields!SalesAmount.Value)</Value></Field>
      </Fields>
    </DataSet>
    <DataSet Name="dsRegions">
      <Query>
        <DataSourceName>SalesDW</DataSourceName>
        <CommandText>SELECT DISTINCT RegionName FROM dbo.DimRegion ORDER BY RegionName</CommandText>
      </Query>
      <Fields>
        <Field Name="RegionName"><DataField>RegionName</DataField><rd:TypeName>System.String</rd:TypeName></Field>
      </Fields>
    </DataSet>
  </DataSets>
  <ReportSections>
    <ReportSection>
      <Body>
        <ReportItems>%(tablix)s</ReportItems>
        <Height>1.2in</Height>
        <Style />
      </Body>
      <Width>8.2in</Width>
      <Page>
        <PageHeader>
          <Height>0.6in</Height>
          <PrintOnFirstPage>true</PrintOnFirstPage>
          <PrintOnLastPage>true</PrintOnLastPage>
          <ReportItems>%(title)s</ReportItems>
          <Style><Border><Style>None</Style></Border></Style>
        </PageHeader>
        <PageFooter>
          <Height>0.3in</Height>
          <PrintOnFirstPage>true</PrintOnFirstPage>
          <PrintOnLastPage>true</PrintOnLastPage>
          <ReportItems>%(footer)s</ReportItems>
          <Style />
        </PageFooter>
        <PageHeight>8.27in</PageHeight>
        <PageWidth>11.69in</PageWidth>
        <LeftMargin>0.5in</LeftMargin>
        <RightMargin>0.5in</RightMargin>
        <TopMargin>0.5in</TopMargin>
        <BottomMargin>0.5in</BottomMargin>
        <Style />
      </Page>
    </ReportSection>
  </ReportSections>
  <ReportParameters>
    <ReportParameter Name="StartDate">
      <DataType>DateTime</DataType>
      <DefaultValue><Values><Value>=DateSerial(Year(Today()), Month(Today()) - 1, 1)</Value></Values></DefaultValue>
      <Prompt>Start date</Prompt>
    </ReportParameter>
    <ReportParameter Name="EndDate">
      <DataType>DateTime</DataType>
      <DefaultValue><Values><Value>=DateAdd("d", -1, DateSerial(Year(Today()), Month(Today()), 1))</Value></Values></DefaultValue>
      <Prompt>End date</Prompt>
    </ReportParameter>
    <ReportParameter Name="Region">
      <DataType>String</DataType>
      <DefaultValue><DataSetReference><DataSetName>dsRegions</DataSetName><ValueField>RegionName</ValueField></DataSetReference></DefaultValue>
      <Prompt>Region</Prompt>
      <ValidValues><DataSetReference><DataSetName>dsRegions</DataSetName><ValueField>RegionName</ValueField><LabelField>RegionName</LabelField></DataSetReference></ValidValues>
      <MultiValue>true</MultiValue>
    </ReportParameter>
  </ReportParameters>
  <ReportParametersLayout>
    <GridLayoutDefinition>
      <NumberOfColumns>3</NumberOfColumns>
      <NumberOfRows>1</NumberOfRows>
      <CellDefinitions>
        <CellDefinition><ColumnIndex>0</ColumnIndex><RowIndex>0</RowIndex><ParameterName>StartDate</ParameterName></CellDefinition>
        <CellDefinition><ColumnIndex>1</ColumnIndex><RowIndex>0</RowIndex><ParameterName>EndDate</ParameterName></CellDefinition>
        <CellDefinition><ColumnIndex>2</ColumnIndex><RowIndex>0</RowIndex><ParameterName>Region</ParameterName></CellDefinition>
      </CellDefinitions>
    </GridLayoutDefinition>
  </ReportParametersLayout>
  <InitialPageName>Sales by Region</InitialPageName>
  <rd:ReportUnitType>Inch</rd:ReportUnitType>
  <rd:ReportID>%(rid)s</rd:ReportID>
</Report>
''' % {"tablix": tablix, "title": title, "footer": footer, "ds1": uuid.uuid4(), "ds2": uuid.uuid4(), "rid": uuid.uuid4()}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(rdl)


# ----------------------------------------------------------------------------
# PBIR exemplar (thin report on a published semantic model)
# ----------------------------------------------------------------------------

def _lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def _col(entity, prop):
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
            "queryRef": "%s.%s" % (entity, prop), "nativeQueryRef": prop}


def _measure(entity, prop):
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
            "queryRef": "%s.%s" % (entity, prop), "nativeQueryRef": prop}


def _visual(name, vtype, pos, query_state, title, objects=None, sort=None):
    v = {"visualType": vtype, "query": {"queryState": query_state},
         "visualContainerObjects": {"title": [{"properties": {"show": _lit("true"), "text": _lit("'%s'" % title),
                                                               "fontSize": _lit("12D"), "bold": _lit("true")}}]},
         "drillFilterOtherVisuals": True}
    if sort:
        v["query"]["sortDefinition"] = sort
    if objects:
        v["objects"] = objects
    return {"$schema": SCHEMA + "item/report/definition/visualContainer/2.13.0/schema.json",
            "name": name, "position": dict(pos, z=pos.get("z", 0), tabOrder=pos.get("tabOrder", 0)), "visual": v}


def pbip_sample_files(report_name="Sales Overview"):
    page_id = "a3f1c2d4e5b6a7c8d9e0"
    files = {}
    root = report_name + ".Report/"
    files[report_name + ".pbip"] = {"$schema": SCHEMA + "pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
                                    "artifacts": [{"report": {"path": report_name + ".Report"}}],
                                    "settings": {"enableAutoRecovery": True}}
    files[root + ".platform"] = {"$schema": SCHEMA + "gitIntegration/platformProperties/2.0.0/schema.json",
                                 "metadata": {"type": "Report", "displayName": report_name},
                                 "config": {"version": "2.0", "logicalId": str(uuid.uuid4())}}
    files[root + "definition.pbir"] = {
        "$schema": SCHEMA + "item/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
        "datasetReference": {"byConnection": {"connectionString":
            'Data Source="powerbi://api.powerbi.com/v1.0/myorg/Sales Analytics";initial catalog="Sales Analytics Model";'
            'access mode=readonly;integrated security=ClaimsToken;semanticmodelid=' + MODEL_ID}}}
    files[root + "definition/version.json"] = {"$schema": SCHEMA + "item/report/definition/versionMetadata/1.0.0/schema.json",
                                               "version": "2.0.0"}
    ver = {"visual": "2.13.0", "report": "3.3.0", "page": "2.1.0"}
    files[root + "definition/report.json"] = {
        "$schema": SCHEMA + "item/report/definition/report/3.3.0/schema.json",
        "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": ver, "type": "SharedResources"},
                            "customTheme": {"name": "ContosoCorporate.json", "reportVersionAtImport": ver, "type": "RegisteredResources"}},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "ContosoCorporate.json", "path": "ContosoCorporate.json", "type": "CustomTheme"}]}],
        "filterConfig": {"filters": [{"name": "f0a1b2c3d4e5f6a7b8c9", "field": {"Column": {"Expression": {"SourceRef": {"Entity": "Geography"}}, "Property": "Region"}}, "type": "Categorical"}]},
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized"}}
    files[root + "definition/pages/pages.json"] = {"$schema": SCHEMA + "item/report/definition/pagesMetadata/1.1.0/schema.json",
                                                   "pageOrder": [page_id], "activePageName": page_id}
    files[root + "definition/pages/%s/page.json" % page_id] = {
        "$schema": SCHEMA + "item/report/definition/page/2.1.0/schema.json", "name": page_id,
        "displayName": "Overview", "displayOption": "FitToPage", "height": 720, "width": 1280,
        "objects": {"background": [{"properties": {"color": {"solid": {"color": _lit("'#F7F9FC'")}}, "transparency": _lit("0D")}}]}}
    visuals = [
        _visual("b1c2d3e4f5a6b7c8d9e0", "card", {"x": 24, "y": 24, "width": 280, "height": 140},
                {"Values": {"projections": [_measure("Sales", "Total Sales")]}}, "Total Sales",
                objects={"labels": [{"properties": {"fontSize": _lit("28D")}}]}),
        _visual("c2d3e4f5a6b7c8d9e0f1", "clusteredColumnChart", {"x": 320, "y": 24, "width": 620, "height": 320, "z": 1000, "tabOrder": 1000},
                {"Category": {"projections": [_col("Geography", "Region")]}, "Y": {"projections": [_measure("Sales", "Total Sales")]}},
                "Sales by Region",
                objects={"dataPoint": [{"properties": {"fill": {"solid": {"color": {"expr": {"ThemeDataColor": {"ColorId": 2, "Percent": 0}}}}}},
                                        "selector": {"metadata": "Sales.Total Sales"}}]},
                sort={"sort": [{"field": _measure("Sales", "Total Sales")["field"], "direction": "Descending"}], "isDefaultSort": True}),
        _visual("d3e4f5a6b7c8d9e0f1a2", "tableEx", {"x": 24, "y": 360, "width": 916, "height": 336, "z": 2000, "tabOrder": 2000},
                {"Values": {"projections": [_col("Geography", "Region"), _col("Product", "Category"),
                                            _measure("Sales", "Total Units"), _measure("Sales", "Total Sales")]}},
                "Sales Detail"),
        _visual("e4f5a6b7c8d9e0f1a2b3", "slicer", {"x": 960, "y": 24, "width": 296, "height": 120, "z": 3000, "tabOrder": 3000},
                {"Values": {"projections": [_col("Geography", "Region")]}}, "Region",
                objects={"data": [{"properties": {"mode": _lit("'Dropdown'")}}]}),
    ]
    for v in visuals:
        files[root + "definition/pages/%s/visuals/%s/visual.json" % (page_id, v["name"])] = v
    files[root + "StaticResources/SharedResources/BaseThemes/CY24SU10.json"] = {
        "name": "CY24SU10", "dataColors": ["#118DFF", "#12239E", "#E66C37", "#6B007B", "#E044A7", "#744EC2"],
        "foreground": "#252423", "background": "#FFFFFF", "tableAccent": "#118DFF"}
    files[root + "StaticResources/RegisteredResources/ContosoCorporate.json"] = {
        "name": "Contoso Corporate", "dataColors": ["#1F4E78", "#2E75B6", "#9DC3E6", "#C55A11", "#F4B183", "#548235"],
        "foreground": "#262626", "background": "#FFFFFF", "tableAccent": "#1F4E78",
        "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": "#1F4E78"},
                        "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": "#262626"}}}
    return files


def build_pbip_sample(path):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, doc in pbip_sample_files().items():
            z.writestr(name, json.dumps(doc, indent=2))


# ----------------------------------------------------------------------------
# PBIT (template) with an import model and legacy report layout
# ----------------------------------------------------------------------------

def build_pbit_sample(path):
    model = {
        "name": str(uuid.uuid4()), "compatibilityLevel": 1567,
        "model": {
            "culture": "en-US",
            "tables": [
                {"name": "Sales", "columns": [
                    {"name": "SalesAmount", "dataType": "decimal", "sourceColumn": "SalesAmount", "formatString": "#,0.00"},
                    {"name": "Units", "dataType": "int64", "sourceColumn": "Units"},
                    {"name": "Cost", "dataType": "decimal", "sourceColumn": "Cost"},
                    {"name": "RegionKey", "dataType": "int64", "sourceColumn": "RegionKey", "isHidden": True}],
                 "partitions": [{"name": "Sales", "mode": "import", "source": {"type": "m", "expression": [
                     "let", "    Source = Sql.Database(ServerName, \"SalesDW\"),",
                     "    dbo_FactSales = Source{[Schema=\"dbo\",Item=\"FactSales\"]}[Data]", "in", "    dbo_FactSales"]}}],
                 "measures": [{"name": "Total Sales", "expression": "SUM(Sales[SalesAmount])", "formatString": "#,0.00"},
                              {"name": "Total Units", "expression": "SUM(Sales[Units])", "formatString": "#,0"},
                              {"name": "Margin %", "expression": "DIVIDE([Total Sales] - SUM(Sales[Cost]), [Total Sales])", "formatString": "0.0%"}]},
                {"name": "Geography", "columns": [{"name": "Region", "dataType": "string", "sourceColumn": "RegionName"},
                                                  {"name": "RegionKey", "dataType": "int64", "sourceColumn": "RegionKey"}],
                 "partitions": [{"name": "Geography", "mode": "import", "source": {"type": "m", "expression":
                     "let\n    Source = Sql.Database(ServerName, \"SalesDW\"),\n    dbo_DimRegion = Source{[Schema=\"dbo\",Item=\"DimRegion\"]}[Data]\nin\n    dbo_DimRegion"}}]},
                {"name": "Product", "columns": [{"name": "Category", "dataType": "string", "sourceColumn": "Category"}],
                 "partitions": [{"name": "Product", "mode": "import", "source": {"type": "m", "expression":
                     "let\n    Source = SharePoint.Files(\"https://contoso.sharepoint.com/sites/Finance\", [ApiVersion = 15]),\n    file = Source{[Name=\"ProductMap.xlsx\"]}[Content],\n    wb = Excel.Workbook(file)\nin\n    wb"}}]}],
            "relationships": [{"name": str(uuid.uuid4()), "fromTable": "Sales", "fromColumn": "RegionKey",
                               "toTable": "Geography", "toColumn": "RegionKey"}],
            "expressions": [{"name": "ServerName", "kind": "m",
                             "expression": "\"sql-prod-01.contoso.local\" meta [IsParameterQuery=true, Type=\"Text\", IsParameterQueryRequired=true]"}]}}
    layout = {
        "id": 0, "config": json.dumps({"themeCollection": {"baseTheme": {"name": "CY24SU10"},
                                                           "customTheme": {"name": "ContosoCorporate.json"}}}),
        "sections": [{"name": "ReportSection", "displayName": "Overview", "width": 1280, "height": 720,
                      "visualContainers": [
                          {"x": 20, "y": 20, "z": 0, "width": 300, "height": 150, "config": json.dumps({
                              "name": "v1", "singleVisual": {"visualType": "card",
                                                            "projections": {"Values": [{"queryRef": "Sales.Total Sales"}]},
                                                            "prototypeQuery": {"Version": 2, "From": [{"Name": "s", "Entity": "Sales", "Type": 0}],
                                                                               "Select": [{"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Total Sales"}, "Name": "Sales.Total Sales"}]},
                                                            "vcObjects": {"title": [{"properties": {"text": {"expr": {"Literal": {"Value": "'Total Sales'"}}}}}]}}})},
                          {"x": 340, "y": 20, "z": 1, "width": 600, "height": 320, "config": json.dumps({
                              "name": "v2", "singleVisual": {"visualType": "clusteredBarChart",
                                                            "projections": {"Category": [{"queryRef": "Geography.Region"}], "Y": [{"queryRef": "Sales.Total Sales"}]},
                                                            "prototypeQuery": {"Version": 2, "From": [{"Name": "g", "Entity": "Geography", "Type": 0}, {"Name": "s", "Entity": "Sales", "Type": 0}],
                                                                               "Select": [{"Column": {"Expression": {"SourceRef": {"Source": "g"}}, "Property": "Region"}, "Name": "Geography.Region"},
                                                                                          {"Measure": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "Total Sales"}, "Name": "Sales.Total Sales"}]}}})}]}]}
    theme = {"name": "Contoso Corporate", "dataColors": ["#1F4E78", "#2E75B6", "#9DC3E6"], "background": "#FFFFFF",
             "foreground": "#262626", "tableAccent": "#1F4E78"}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="utf-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="" /><Override PartName="/Version" ContentType="" /><Override PartName="/DataModelSchema" ContentType="" /><Override PartName="/Report/Layout" ContentType="" /></Types>')
        z.writestr("Version", "1.28".encode("utf-16-le"))
        z.writestr("DataModelSchema", json.dumps(model).encode("utf-16-le"))
        z.writestr("Report/Layout", json.dumps(layout).encode("utf-16-le"))
        z.writestr("Report/StaticResources/RegisteredResources/ContosoCorporate.json", json.dumps(theme))
