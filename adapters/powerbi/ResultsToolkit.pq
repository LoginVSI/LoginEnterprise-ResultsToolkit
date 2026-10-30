section ResultsToolkit;

// Independently authored. Credentials belong to Power Query, never to report parameters.
[DataSource.Kind="ResultsToolkit", Publish="ResultsToolkit.Publish"]
shared ResultsToolkit.Rows = Value.ReplaceType(RowsImpl, RowsType);

[DataSource.Kind="ResultsToolkit"]
shared ResultsToolkit.Native = Value.ReplaceType(NativeImpl, RowsType);

[DataSource.Kind="ResultsToolkit"]
shared ResultsToolkit.Ping = Value.ReplaceType((origin as text) as any => Get(Origin(origin), "system/version", [], 0), type function (origin as (Uri.Type)) as any);

RowsType = type function (
    origin as (Uri.Type),
    configuration as (type text meta [DataSource.Path=false, Documentation.FieldCaption="Nonsecret selection JSON"])
) as table;

ResultsToolkit = [
    TestConnection = (dataSourcePath) => {"ResultsToolkit.Ping", dataSourcePath},
    Authentication = [Key = [KeyLabel="Login Enterprise API token"]],
    Label = "Login Enterprise Results Toolkit (community preview)"
];

ResultsToolkit.Publish = [Beta=true, Category="Other", ButtonText={"Results Toolkit", "Read selected Login Enterprise results"}, SourceImage=ResultsToolkit.Icons, SourceTypeImage=ResultsToolkit.Icons];
ResultsToolkit.Icons = [Icon16={Extension.Contents("icon16.png")}, Icon32={Extension.Contents("icon32.png")}];

Origin = (origin as text) as text =>
    let p = Uri.Parts(origin),
        safe = p[Scheme] = "https" and p[Host] <> "" and List.Contains({"", "/"}, p[Path])
            and Record.FieldCount(p[Query]) = 0 and p[Fragment] = "" and not Text.Contains(origin, "@")
    in if safe then Text.TrimEnd(origin, "/") else error Error.Record("Origin", "Use a trusted HTTPS origin only.", null);

Id = (value as text) as text =>
    let lower = Text.Lower(value), pieces = Text.Split(lower, "-")
    in if List.Transform(pieces, Text.Length) = {8,4,4,4,12} and Text.Select(lower, {"0".."9", "a".."f", "-"}) = lower
       then lower else error Error.Record("Selection", "Explicit UUID required.", null);

// A finite preview refresh: <=4 results, <=10 sessions/result, <=2 pages/sequence,
// <=3 attempts/request. At most 375 HTTP attempts, including version metadata.
Get = (origin as text, path as text, query as record, attempt as number, optional deadline as nullable datetimezone) as any =>
    let end = if deadline = null then DateTimeZone.UtcNow()+#duration(0,0,5,0) else deadline,
        remaining = Duration.TotalSeconds(end-DateTimeZone.UtcNow()),
        response = if remaining <= 0 then error Error.Record("Deadline", "Refresh deadline exceeded; narrow selection.", null)
          else Web.Contents(origin, [RelativePath="publicApi/v8-preview/" & path,
            Query=query, Headers=[Accept="application/json", Authorization="Bearer " & Extension.CurrentCredential()[Key]],
            ManualCredentials=true, ManualStatusHandling=List.RemoveItems({300..599},{401,403}),
            Timeout=#duration(0,0,0,List.Min({20,remaining})), IsRetry=attempt > 0]),
        metadata = Value.Metadata(response), status = Record.FieldOrDefault(metadata, "Response.Status", 200),
        headers = Record.FieldOrDefault(metadata, "Headers", []),
        retryHeader = Record.FieldOrDefault(headers, "Retry-After", null),
        parsedSeconds = try Number.FromText(retryHeader) otherwise null,
        parsedDate = try DateTimeZone.FromText(retryHeader) otherwise null,
        delay = if parsedSeconds <> null then parsedSeconds else if parsedDate <> null
                then Duration.TotalSeconds(parsedDate - DateTimeZone.UtcNow()) else Number.Power(2,attempt),
        retry = List.Contains({429,502,503,504},status) and attempt < 2,
        data = if DateTimeZone.UtcNow() >= end then error Error.Record("Deadline", "Refresh deadline exceeded.", null)
               else if retry then
                 if delay > 30 then error Error.Record("HTTP", "Retry-After exceeds bounded wait; retry later.", status)
                 else if delay >= Duration.TotalSeconds(end-DateTimeZone.UtcNow()) then error Error.Record("Deadline", "Retry exceeds remaining refresh deadline.", null)
                 else Function.InvokeAfter(() => @Get(origin,path,query,attempt+1,end), #duration(0,0,0,List.Max({0,delay})))
               else if status >= 300 and status < 400 then error Error.Record("Redirect", "Redirect refused.", null)
               else if status <> 200 then error Error.Record("HTTP", "Result endpoint failed.", status)
               else (try Json.Document(response) otherwise error Error.Record("Contract", "Invalid JSON response.", null))
    in if data = null then error Error.Record("Contract", "Null is not an empty dataset.", null) else data;

Page = (origin as text, path as text, query as record, offset as number, total as nullable number, page as number, deadline as datetimezone) as list =>
    if page >= 2 then error Error.Record("Paging", "Page bound exceeded; narrow the selection.", null)
    else let response = Get(origin,path,Record.Combine({query,[count="100", offset=Text.From(offset), direction="asc", includeTotalCount="true"]}),0,deadline),
        items = Record.FieldOrDefault(response,"items",null), actualOffset = Record.FieldOrDefault(response,"offset",null),
        actualTotal = Record.FieldOrDefault(response,"totalCount",null),
        valid = Value.Is(items,type list) and actualOffset = offset
                and (actualTotal = null or (Value.Is(actualTotal,type number) and actualTotal >= 0 and Number.RoundDown(actualTotal)=actualTotal))
                and (total = null or total = actualTotal),
        n = if valid then List.Count(items) else error Error.Record("Paging", "Invalid or changing paging envelope.", null),
        nextOffset = offset+n,
        next = if actualTotal <> null and nextOffset > actualTotal then error Error.Record("Paging", "More rows than totalCount.", null)
               else if actualTotal <> null and nextOffset = actualTotal then {}
               else if n < 100 then
                    if actualTotal <> null and nextOffset < actualTotal then error Error.Record("Paging", "Truncated page.", null) else {}
               else @Page(origin,path,query,nextOffset,actualTotal,page+1,deadline),
        combined = List.Combine({items,next})
    in if List.Count(List.Distinct(combined)) <> List.Count(combined) then error Error.Record("Paging", "Overlapping rows; recapture a stable window.", null) else combined;

EmptyRows = type table [row_kind=text, scenario=text, run_id=text, session_id=nullable text,
    execution_id=nullable text, metric_key=nullable text, metric_name=nullable text, unit=nullable text,
    instance=nullable text, field_name=nullable text, value=nullable number, state=nullable text,
    timestamp=nullable text, source_json=text, configuration_scope=nullable text,
    timestamp_utc=nullable text, window_start=nullable text, window_end=nullable text,
    observation_present=text, availability=nullable text];

// The raw record stays inspectable. Authentication material is never an output field.
SafeSource = (value as any) as any =>
    if Value.Is(value,type record) then Record.FromList(List.Transform(List.Sort(Record.FieldNames(value)), (k) =>
        if List.AnyTrue(List.Transform({"authorization","password","secret","token","cookie","apikey"}, (s) => Text.Contains(Text.Replace(Text.Lower(k),"_",""),s)))
        then "[REDACTED]" else @SafeSource(Record.Field(value,k))),List.Sort(Record.FieldNames(value)))
    else if Value.Is(value,type list) then List.Transform(value, each @SafeSource(_))
    else if Value.Is(value,type text) then
        if Text.Contains(Text.Lower(value), "bearer ") then "[REDACTED auth material]" else Text.Replace(value, Extension.CurrentCredential()[Key], "[REDACTED]")
    else value;

Row = (kind as text, scenario as text, run as text, rawSource as record, window as record,
       optional metric as nullable record) as record =>
    let actualRun = Record.FieldOrDefault(rawSource,"testRunId",null),
        source = if actualRun <> null and actualRun <> run then error Error.Record("Identity", "Source result identity differs from selection.", null) else SafeSource(rawSource),
        m = if metric = null then [] else metric,
        rawValue = if kind="measurement" then Record.FieldOrDefault(source,"duration",null)
                   else Record.FieldOrDefault(source,"measurement",null),
        value = if Value.Is(rawValue,type number) and not Number.IsNaN(rawValue) and rawValue <> #infinity and rawValue <> -#infinity and not List.Contains(Record.FieldOrDefault(m,"exclude_values",{}),rawValue)
                then rawValue else null,
        groupFields = List.Sort(Record.FieldOrDefault(m,"group_by",{})),
        group = Record.SelectFields(source,groupFields,MissingField.UseNull),
        stamp = Record.FieldOrDefault(source,"timestamp",Record.FieldOrDefault(source,"created",null)),
        explicitZone = stamp <> null and (Text.EndsWith(stamp,"Z") or (Text.Length(stamp)>=6 and List.Contains({"+","-"}, Text.Start(Text.End(stamp,6),1)))),
        utc = if explicitZone then (try DateTimeZone.ToText(DateTimeZone.SwitchZone(DateTimeZone.FromText(stamp),0),"yyyy-MM-ddTHH:mm:ss.fffZ") otherwise null) else null
    in [row_kind=kind,scenario=scenario,run_id=run,
        session_id=Record.FieldOrDefault(source,"userSessionId",Record.FieldOrDefault(source,"userSessionKey",if kind="session" then Record.FieldOrDefault(source,"id",null) else null)),
        execution_id=Record.FieldOrDefault(source,"appExecutionId",if kind="execution" then Record.FieldOrDefault(source,"id",null) else null),
        metric_key=if metric=null then null else m[name] & " / " & Text.FromBinary(Json.FromValue(group),TextEncoding.Utf8),
        metric_name=Record.FieldOrDefault(m,"name",null),
        unit=if kind="session_metric" then Record.FieldOrDefault(source,"unit",null) else Record.FieldOrDefault(m,"unit",null),
        instance=Record.FieldOrDefault(source,"instance",null), field_name=Record.FieldOrDefault(source,"fieldName",null),
        value=if metric=null then null else value,
        state=if kind="session" then Record.FieldOrDefault(source,"loginState",null) else Record.FieldOrDefault(source,"state",null),
        timestamp=stamp,timestamp_utc=utc,
        source_json=Text.FromBinary(Json.FromValue(SafeSource(source)),TextEncoding.Utf8),
        configuration_scope=if kind="run" then (if Record.FieldOrDefault(source,"type",null)="ContinuousTest" then "current"
                            else if Record.FieldOrDefault(source,"testConfigurationSnapshot",null) <> null then "historical" else "unavailable") else null,
        window_start=Record.FieldOrDefault(window,"from",null),window_end=Record.FieldOrDefault(window,"to",null),
        observation_present=if Record.HasFields(rawSource,"availability") then "false" else "true",
        availability=Record.FieldOrDefault(source,"availability",null)];

EntityRows = (rows as list) as list =>
    let byId = List.Distinct(rows,each [id])
    in if List.Count(List.Distinct(rows)) <> List.Count(byId) then error Error.Record("Identity", "Entity versions changed; recapture a stable window.", null) else byId;

IdentityRows = (rows as list, id as text) as list =>
    if List.AnyTrue(List.Transform(rows, (r) => Record.FieldOrDefault(r,"testRunId",null) <> null and Record.Field(r,"testRunId") <> id))
    then error Error.Record("Identity", "Source result identity differs from selection.", null) else rows;

Fetch = (origin as text, kind as text, scenario as text, runId as text, window as record, metrics as list, deadline as datetimezone) as list =>
    let id = Id(runId), prefix = "test-runs/" & id & "/",
        run = if kind="ContinuousTest" then Get(origin,"tests/" & id,[include="all"],0,deadline)
              else Get(origin,"test-runs/" & id,[include="testRunConfigurationSnapshot"],0,deadline),
        checkedRun = if Record.FieldOrDefault(run,"type",null) <> kind or Record.FieldOrDefault(run,"id",null) <> id then error Error.Record("Selection","Returned identity/type differs from selection.",null)
                     else if kind <> "ContinuousTest" and Record.FieldOrDefault(run,"finished",null)=null then error Error.Record("Selection","Select completed runs.",null) else run,
        sessionUnion = List.Buffer(List.Combine(List.Transform(if Record.HasFields(window,"from") then {"loggedIn","created"} else {"created"}, (mode) => Page(origin,prefix & "user-sessions",Record.Combine({window,[filterType=mode]}),0,null,0,deadline)))),
        sessionIds = EntityRows(sessionUnion),
        sessions = if List.Count(sessionIds) > 10 then error Error.Record("Bounds", "More than ten sessions; narrow the selection.", null) else List.Buffer(sessionIds),
        executions = List.Buffer(EntityRows(List.Combine(List.Transform(sessions, (s) => Page(origin,prefix & "user-sessions/" & Id(s[id]) & "/app-executions",window,0,null,0,deadline))))),
        measurements = List.Buffer(Page(origin,prefix & "measurements",Record.Combine({window,[include="all"]}),0,null,0,deadline)),
        settings = if kind="ContinuousTest" then checkedRun else Record.FieldOrDefault(checkedRun,"testConfigurationSnapshot",[]),
        disabled = kind <> "ContinuousTest" and Record.FieldOrDefault(if settings=null then [] else settings,"sessionMetricsEnabled",null)=false,
        sessionMetrics = List.Buffer(if disabled then {} else if List.AnyTrue(List.Transform(metrics, each [table]="session_metrics")) then Page(origin,"user-session-metrics/" & id,Record.Combine({window,[orderBy="timestamp"]}),0,null,0,deadline) else {}),
        events = Page(origin,prefix & "events",window,0,null,0,deadline),
        metricRows = List.Combine(List.Transform(metrics,(m) =>
            let sourceRows = if m[table]="measurements" then measurements else sessionMetrics,
                matched = List.Select(sourceRows,(r) => List.AllTrue(List.Transform(Record.FieldNames(m[match]),(k) => Record.FieldOrDefault(r,k,null)=Record.Field(m[match],k))))
            in List.Transform(if List.IsEmpty(matched) then {[availability=if m[table]="session_metrics" and disabled then "disabled" else "configured-but-no-measurements",state="unavailable"]} else matched,(r) => if m[table]="session_metrics" and Record.FieldOrDefault(r,"availability",null)=null and Record.FieldOrDefault(r,"unit",null) <> m[unit]
                then error Error.Record("Unit","Source unit differs from configured unit.",null)
                else Row(if m[table]="measurements" then "measurement" else "session_metric",scenario,id,r,window,m)))),
        checkedSources = List.Count(IdentityRows(List.Combine({sessions,executions,measurements,sessionMetrics,events}),id)),
        rows = if checkedSources < 0 then {} else List.Combine({{Row("run",scenario,id,checkedRun,window)},
            List.Transform(sessions,each Row("session",scenario,id,_,window)),
            List.Transform(executions,each Row("execution",scenario,id,_,window)),
            List.Transform(events,each Row("event",scenario,id,_,window)), metricRows})
    in rows;

RowsImpl = (origin as text, configuration as text) as table =>
    let host = Origin(origin), rawConfig = Json.Document(configuration),
        single = Record.FieldOrDefault(rawConfig,"schema_version",null) = "acquisition/2",
        requestedSides = if single then {rawConfig[selected]} else {rawConfig[baseline],rawConfig[candidate]},
        config = if not List.Contains({"acquisition/1","acquisition/2"},Record.FieldOrDefault(rawConfig,"schema_version",null)) or not List.Contains({"LoadTest","ApplicationTest","ContinuousTest"},rawConfig[test_type])
                 or (single and (Record.HasFields(rawConfig,"baseline") or Record.HasFields(rawConfig,"candidate") or List.Count(rawConfig[selected][ids]) <> 1))
                 or List.AnyTrue(List.Transform(requestedSides,each List.Count([ids]) < 1)) or List.Sum(List.Transform(requestedSides,each List.Count([ids]))) > 4 then error Error.Record("Selection","Invalid acquisition contract or selection bounds (four results total).",null) else rawConfig,
        end = DateTimeZone.FixedUtcNow(), hours = Record.FieldOrDefault(config,"rolling_hours",null),
        window = if hours <> null then [from=DateTimeZone.ToText(end-#duration(0,hours,0,0),"yyyy-MM-ddTHH:mm:ss.fffZ"),to=DateTimeZone.ToText(end,"yyyy-MM-ddTHH:mm:ss.fffZ")]
                 else if Record.FieldOrDefault(config,"start",null) <> null then [from=config[start],to=config[end]] else [],
        sides = if single then {config[selected]} else {config[baseline],config[candidate]},
        deadline = end+#duration(0,0,5,0),
        records = List.Combine(List.Transform(sides,(s) => List.Combine(List.Transform(s[ids],(id) => Fetch(host,config[test_type],s[label],id,window,config[metrics],deadline))))),
        version = Get(host,"system/version",[],0,deadline),
        // Row emits every column. UseNull rejects this type's required non-nullable columns.
        // Optional values are already explicit nulls; a missing constructed field is a contract error.
        raw = Table.Buffer(Table.FromRecords(List.Combine({{Row("metadata","Appliance","",version,window)},records}),EmptyRows,MissingField.Error)),
        errorCheck = Table.RowCount(Table.SelectRowsWithErrors(raw)),
        result = if errorCheck > 0 then error Error.Record("Contract", "Acquisition contains invalid cells; refresh refused.", null) else Table.Distinct(raw),
        captured = Table.AddColumn(result,"captured_at",each DateTimeZone.ToText(end,"yyyy-MM-ddTHH:mm:ss.fffZ"),type text),
        dedup = Table.AddColumn(captured,"deduplicated_rows",each Text.From(Table.RowCount(raw)-Table.RowCount(result)),type text),
        complete = Table.AddColumn(dedup,"capture_status",each "complete selected endpoint acquisition",type text)
    in complete;

// Native whole-run scores from the Load result overview. A separate table so the timestamped
// rows from ResultsToolkit.Rows keep their own grain. Values are never computed or averaged here.
NativeEmpty = type table [scenario=text, run_id=text, metric_name=text, result_id=text,
    result_group=nullable text, unit=text, value=nullable number, state=nullable text,
    display_value=text, availability=text, test_name=nullable text, counter=nullable number,
    run_state=nullable text, test_result=nullable text, score_grain=text, provenance=text,
    source_endpoint=text, source_json=text];

NativeDisplay = (resultId as text, value as nullable number, state as nullable text) as text =>
    let shown = if value = null then null else Text.From(value, "en-US")
    in if shown = null then "unavailable" & (if state = null then "" else " (" & state & ")")
       else if resultId = "vsi_max" and state = "aboveThreshold" then ">" & shown
       else if state <> null and state <> "completed" then shown & " (" & state & ")"
       else shown;

NativeRowsFor = (origin as text, scenario as text, runId as text, metrics as list, deadline as datetimezone) as list =>
    let id = Id(runId),
        run = Get(origin, "test-runs/" & id, [], 0, deadline),
        checkedRun = if Record.FieldOrDefault(run,"type",null) <> "LoadTest" or Record.FieldOrDefault(run,"id",null) <> id
                     then error Error.Record("Selection","Native scores apply to Load results; returned identity/type differs from selection.",null)
                     else if Record.FieldOrDefault(run,"finished",null) = null then error Error.Record("Selection","Select completed runs.",null) else run,
        overview = Get(origin, "load-test-run-overview/" & id, [], 0, deadline),
        entries = Record.FieldOrDefault(overview,"results",null),
        valid = Value.Is(entries,type list) and List.Count(entries) > 0
                and List.AllTrue(List.Transform(entries, (e) => Value.Is(e,type record) and Record.FieldOrDefault(e,"testRunId",null) = id)),
        entry = if valid then List.First(entries) else error Error.Record("Identity","Native overview identity differs from selected run.",null),
        results = Record.FieldOrDefault(entry,"results",[]),
        performance = Record.FieldOrDefault(results,"performance",[]),
        flat = List.Combine({
            List.Transform(Record.FieldOrDefault(performance,"results",{}), (i) => [group="performance", item=i,
                state=if Text.StartsWith(Record.FieldOrDefault(i,"resultId",""),"eux_") then Record.FieldOrDefault(performance,"euxState",null)
                      else if Record.FieldOrDefault(i,"resultId",null) = "vsi_max" then Record.FieldOrDefault(performance,"vsiMaxState",null) else null]),
            List.Transform(Record.FieldOrDefault(results,"loginTime",{}), (i) => [group="loginTime", item=i, state=null]),
            List.Select({[group="appPerformance", item=Record.FieldOrDefault(Record.FieldOrDefault(results,"appPerformanceResult",[]),"totalAppPerformance",null), state=null]}, (a) => a[item] <> null)}),
        rows = List.Transform(metrics, (m) =>
            let wanted = m[match][resultId], group = Record.FieldOrDefault(m[match],"result_group",null),
                hits = List.Select(flat, (f) => Record.FieldOrDefault(f[item],"resultId",null) = wanted and (group = null or f[group] = group)),
                hit = if List.Count(hits) > 1 then error Error.Record("Identity","Native result identity is ambiguous; set match.result_group.",null)
                      else if List.Count(hits) = 1 then hits{0} else null,
                raw = if hit = null then null else Record.FieldOrDefault(hit[item],"value",null),
                value = if Value.Is(raw,type number) and not Number.IsNaN(raw) and raw <> #infinity and raw <> -#infinity then raw else null,
                state = if hit = null then null else hit[state]
            in [scenario=scenario, run_id=id, metric_name=m[name], result_id=wanted, result_group=if hit = null then group else hit[group],
                unit=m[unit], value=value, state=state, display_value=NativeDisplay(wanted, value, state),
                availability=if hit = null then "absent-from-overview" else if value = null then "null-in-overview" else "present",
                test_name=Record.FieldOrDefault(entry,"testName",null), counter=Record.FieldOrDefault(entry,"counter",null),
                run_state=Record.FieldOrDefault(entry,"state",null), test_result=Record.FieldOrDefault(entry,"testResult",null),
                score_grain="native_whole_run", provenance="native_overview", source_endpoint="load-test-run-overview/{id}",
                source_json=Text.FromBinary(Json.FromValue(if hit = null then [] else SafeSource(hit[item])),TextEncoding.Utf8)])
    in if checkedRun = null then {} else rows;

NativeImpl = (origin as text, configuration as text) as table =>
    let host = Origin(origin), rawConfig = Json.Document(configuration),
        single = Record.FieldOrDefault(rawConfig,"schema_version",null) = "acquisition/2",
        sides = if single then {rawConfig[selected]} else {rawConfig[baseline],rawConfig[candidate]},
        metrics = List.Select(rawConfig[metrics], (m) => Record.FieldOrDefault(m,"table",null) = "native_scores"),
        ok = List.Contains({"acquisition/1","acquisition/2"},Record.FieldOrDefault(rawConfig,"schema_version",null))
             and rawConfig[test_type] = "LoadTest" and List.Count(metrics) > 0
             and List.AllTrue(List.Transform(sides, (s) => List.Count(s[ids]) = 1))
             and List.AllTrue(List.Transform(metrics, (m) => Record.FieldOrDefault(m,"semantics",null) = "native_score"
                 and Record.FieldOrDefault(m,"value_field",null) = "value" and Value.Is(Record.FieldOrDefault(Record.FieldOrDefault(m,"match",[]),"resultId",null),type text))),
        config = if ok then rawConfig else error Error.Record("Selection","Native scores need a Load selection with one result per side and native_scores metrics.",null),
        end = DateTimeZone.FixedUtcNow(), deadline = end+#duration(0,0,5,0),
        records = List.Combine(List.Transform(sides, (s) => NativeRowsFor(host, s[label], s[ids]{0}, metrics, deadline))),
        raw = Table.Buffer(Table.FromRecords(records, NativeEmpty, MissingField.Error)),
        errorCheck = Table.RowCount(Table.SelectRowsWithErrors(raw)),
        result = if errorCheck > 0 then error Error.Record("Contract", "Native acquisition contains invalid cells; refresh refused.", null) else raw,
        captured = Table.AddColumn(result,"captured_at",each DateTimeZone.ToText(end,"yyyy-MM-ddTHH:mm:ss.fffZ"),type text),
        complete = Table.AddColumn(captured,"capture_status",each "complete native overview acquisition",type text)
    in complete;
