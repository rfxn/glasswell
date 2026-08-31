- [Fix] nm_wells: declare the staged header frame's dtypes instead of letting polars infer
      them per batch. The staging table is 39 text columns and one integer, but a column null
      across the inference window is typed Null, so the first state code below it refused the
      whole frame and failed the promotion that opens the New Mexico gate
