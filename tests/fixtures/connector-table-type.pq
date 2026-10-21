let
    RowType = type table [row_kind=text, run_id=text, value=nullable number],
    Complete = Table.Buffer(Table.FromRecords({[row_kind="timer", run_id="synthetic", value=null]}, RowType, MissingField.Error)),
    Missing = try Table.Buffer(Table.FromRecords({[row_kind="timer", value=0]}, RowType, MissingField.Error)),
    Result = if Table.RowCount(Complete) <> 1 or Complete{0}[value] <> null or not Missing[HasError]
        then error "Required fields or missing-value semantics failed."
        else Complete
in Result
