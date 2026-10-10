section ResultsToolkit;

// Independently authored. Credentials belong to Power Query, never to report parameters.
[DataSource.Kind="ResultsToolkit", Publish="ResultsToolkit.Publish"]
shared ResultsToolkit.Rows = Value.ReplaceType(RowsImpl, RowsType);

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

Get = (origin as text, path as text, query as record, attempt as number) as any =>
    let attempted = try Web.Contents(origin, [RelativePath="publicApi/v8-preview/" & path,
            Query=query, Headers=[Accept="application/json", Authorization="Bearer " & Extension.CurrentCredential()[Key]],
            ManualCredentials=true, ManualStatusHandling={300..399,401,403,404,405,429,500,502,503,504},
            Timeout=#duration(0,0,0,20), IsRetry=attempt > 0]),
        response = if attempted[HasError] then error Error.Record("Transport", "Trusted HTTPS request failed; check certificate and timeout.", null) else attempted[Value],
        metadata = Value.Metadata(response), status = Record.FieldOrDefault(metadata, "Response.Status", 200),
        headers = Record.FieldOrDefault(metadata, "Headers", []),
        retryHeader = Record.FieldOrDefault(headers, "Retry-After", null),
        parsedSeconds = try Number.FromText(retryHeader) otherwise null,
        parsedDate = try DateTimeZone.FromText(retryHeader) otherwise null,
        delay = if parsedSeconds <> null then parsedSeconds else if parsedDate <> null
                then Duration.TotalSeconds(parsedDate - DateTimeZone.UtcNow()) else Number.Power(2,attempt),
        retry = List.Contains({429,502,503,504},status) and attempt < 2,
        data = if retry then
                 if delay > 30 then error Error.Record("HTTP", "Retry-After exceeds bounded wait; retry later.", status)
                 else Function.InvokeAfter(() => @Get(origin,path,query,attempt+1), #duration(0,0,0,List.Max({0,delay})))
               else if status = 401 then error Error.Record("Authentication", "401: replace the saved Power Query credential.", null)
               else if status = 403 then error Error.Record("Authorization", "403: credential lacks permission.", null)
               else if status >= 300 and status < 400 then error Error.Record("Redirect", "Redirect refused.", null)
               else if status <> 200 then error Error.Record("HTTP", "Result endpoint failed.", status)
               else (try Json.Document(response) otherwise error Error.Record("Contract", "Invalid JSON response.", null))
    in if data = null then error Error.Record("Contract", "Null is not an empty dataset.", null) else data;

Page = (origin as text, path as text, query as record, offset as number, total as nullable number, page as number) as list =>
    if page >= 100 then error Error.Record("Paging", "Page bound exceeded; narrow the selection.", null)
    else let response = Get(origin,path,Record.Combine({query,[count="100", offset=Text.From(offset), direction="asc", includeTotalCount="true"]}),0),
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
               else @Page(origin,path,query,nextOffset,actualTotal,page+1)
    in List.Combine({items,next});

EmptyRows = type table [row_kind=text, scenario=text, run_id=text, session_id=nullable text,
    execution_id=nullable text, metric_key=nullable text, metric_name=nullable text, unit=nullable text,
    instance=nullable text, field_name=nullable text, value=nullable number, state=nullable text,
    timestamp=nullable text, source_json=text, configuration_scope=nullable text,
    timestamp_utc=nullable text, window_start=nullable text, window_end=nullable text];

// The raw record stays inspectable. Authentication material is never an output field.
SafeSource = (value as any) as any =>
    if Value.Is(value,type record) then Record.FromList(List.Transform(List.Sort(Record.FieldNames(value)), (k) =>
        if List.AnyTrue(List.Transform({"authorization","password","secret","token","cookie"}, (s) => Text.Contains(Text.Lower(k),s)))
        then "[REDACTED]" else @SafeSource(Record.Field(value,k))),List.Sort(Record.FieldNames(value)))
    else if Value.Is(value,type list) then List.Transform(value, each @SafeSource(_))
    else if Value.Is(value,type text) then
        if Text.Contains(Text.Lower(value), "bearer ") then "[REDACTED auth material]" else Text.Replace(value, Extension.CurrentCredential()[Key], "[REDACTED]")
    else value;

Row = (kind as text, scenario as text, run as text, rawSource as record, window as record,
       optional metric as nullable record) as record =>
    let source = SafeSource(rawSource), m = if metric = null then [] else metric,
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
        window_start=Record.FieldOrDefault(window,"from",null),window_end=Record.FieldOrDefault(window,"to",null)];

Fetch = (origin as text, kind as text, scenario as text, runId as text, window as record, metrics as list) as list =>
    let id = Id(runId), prefix = "test-runs/" & id & "/",
        run = if kind="ContinuousTest" then Get(origin,"tests/" & id,[include="all"],0)
              else Get(origin,"test-runs/" & id,[include="testRunConfigurationSnapshot"],0),
        checkedRun = if Record.FieldOrDefault(run,"type",null) <> kind then error Error.Record("Selection","Returned type differs from selection.",null)
                     else if kind <> "ContinuousTest" and Record.FieldOrDefault(run,"finished",null)=null then error Error.Record("Selection","Select completed runs.",null) else run,
        sessions = Page(origin,prefix & "user-sessions",window,0,null,0),
        executions = List.Combine(List.Transform(sessions, (s) => Page(origin,prefix & "user-sessions/" & Id(s[id]) & "/app-executions",window,0,null,0))),
        measurements = Page(origin,prefix & "measurements",Record.Combine({window,[include="all"]}),0,null,0),
        sessionMetrics = if List.AnyTrue(List.Transform(metrics, each [table]="session_metrics")) then Page(origin,"user-session-metrics/" & id,window,0,null,0) else {},
        events = Page(origin,prefix & "events",window,0,null,0),
        metricRows = List.Combine(List.Transform(metrics,(m) =>
            let sourceRows = if m[table]="measurements" then measurements else sessionMetrics,
                matched = List.Select(sourceRows,(r) => List.AllTrue(List.Transform(Record.FieldNames(m[match]),(k) => Record.FieldOrDefault(r,k,null)=Record.Field(m[match],k))))
            in List.Transform(if List.IsEmpty(matched) then {[availability="configured-but-no-measurements",state="unavailable"]} else matched,(r) => if m[table]="session_metrics" and Record.FieldOrDefault(r,"availability",null)=null and Record.FieldOrDefault(r,"unit",null) <> m[unit]
                then error Error.Record("Unit","Source unit differs from configured unit.",null)
                else Row(if m[table]="measurements" then "measurement" else "session_metric",scenario,id,r,window,m)))),
        rows = List.Combine({{Row("run",scenario,id,checkedRun,window)},
            List.Transform(sessions,each Row("session",scenario,id,_,window)),
            List.Transform(executions,each Row("execution",scenario,id,_,window)),
            List.Transform(events,each Row("event",scenario,id,_,window)), metricRows})
    in rows;

RowsImpl = (origin as text, configuration as text) as table =>
    let host = Origin(origin), rawConfig = Json.Document(configuration),
        config = if Record.FieldOrDefault(rawConfig,"schema_version",null) <> "acquisition/1" or not List.Contains({"LoadTest","ApplicationTest","ContinuousTest"},rawConfig[test_type])
                 or List.Count(rawConfig[baseline][ids]) > 20 or List.Count(rawConfig[candidate][ids]) > 20 then error Error.Record("Selection","Invalid acquisition contract or selection bounds.",null) else rawConfig,
        end = DateTimeZone.FixedUtcNow(), hours = Record.FieldOrDefault(config,"rolling_hours",null),
        window = if hours <> null then [from=DateTimeZone.ToText(end-#duration(0,hours,0,0),"yyyy-MM-ddTHH:mm:ss.fffZ"),to=DateTimeZone.ToText(end,"yyyy-MM-ddTHH:mm:ss.fffZ")]
                 else if Record.FieldOrDefault(config,"start",null) <> null then [from=config[start],to=config[end]] else [],
        sides = {config[baseline],config[candidate]},
        records = List.Combine(List.Transform(sides,(s) => List.Combine(List.Transform(s[ids],(id) => Fetch(host,config[test_type],s[label],id,window,config[metrics]))))),
        version = Get(host,"system/version",[],0),
        result = Table.Distinct(Table.FromRecords(List.Combine({{Row("metadata","Appliance","",version,window)},records}),EmptyRows,MissingField.UseNull)),
        captured = Table.AddColumn(result,"captured_at",each DateTimeZone.ToText(end,"yyyy-MM-ddTHH:mm:ss.fffZ"),type text),
        complete = Table.AddColumn(captured,"capture_status",each "complete acquisition",type text)
    in complete;
