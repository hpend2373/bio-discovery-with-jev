# Original interoperability helper; requires CellChat v1/v2 objects and jsonlite.
# Writes complete STORED arrays; upstream filtering cannot be reversed.
export_cellchat <- function(objects, out, contexts = NULL, database_version = "unknown") {
  stopifnot(requireNamespace("jsonlite", quietly = TRUE))
  if (methods::is(objects, "CellChat")) objects <- list(dataset = objects)
  if (!is.list(objects) || is.null(names(objects)) || any(!nzchar(names(objects))) || anyDuplicated(names(objects)))
    stop("Supply a uniquely named list of CellChat objects")
  if (dir.exists(out)) stop("Use a new output directory")
  dir.create(out, recursive = TRUE)
  files <- list(); index <- 0L
  emit <- function(net, lr, context, db, options, object_name) {
    if (!is.array(net$prob) || length(dim(net$prob)) != 3L) stop("Expected group-level 3D net$prob; Spatial CellChat v3 is unsupported")
    if (!identical(dim(net$prob), dim(net$pval)) || !identical(dimnames(net$prob), dimnames(net$pval))) stop("Probability/p-value axes differ")
    if (any(vapply(dimnames(net$prob), is.null, logical(1)))) stop("Missing array axis labels")
    for (level in c("LR")) {
      arr <- net$prob; axes <- dimnames(arr)
      feature <- "interaction_name"
      grid <- expand.grid(source = axes[[1]], target = axes[[2]], interaction_name = axes[[3]], stringsAsFactors = FALSE)
      grid$prob <- as.vector(arr); grid$pval <- as.vector(net$pval)
      at <- match(grid$interaction_name, rownames(lr))
      annotations <- intersect(c("ligand", "receptor", "interaction_name_2", "pathway_name", "annotation", "evidence", "agonist", "antagonist", "co_A_receptor", "co_I_receptor"), names(lr))
      for (nm in annotations) grid[[nm]] <- as.character(lr[[nm]][at])
      # Preserve exact complex/cofactor composition; never split underscore labels.
      components <- function(label, table) {
        if (is.null(table) || is.na(label) || !label %in% rownames(table)) return(NA_character_)
        paste(as.character(unlist(table[label, , drop = FALSE])), collapse = "|")
      }
      for (nm in intersect(c("ligand", "receptor"), names(grid)))
        grid[[paste0(nm, "_complex_components")]] <- vapply(grid[[nm]], components, character(1), table = db$complex)
      for (nm in intersect(c("agonist", "antagonist", "co_A_receptor", "co_I_receptor"), names(grid)))
        grid[[paste0(nm, "_components")]] <- vapply(grid[[nm]], components, character(1), table = db$cofactor)
      for (nm in names(context)) grid[[nm]] <- rep(as.character(context[[nm]]), nrow(grid))
      index <<- index + 1L; filename <- sprintf("cellchat-%04d.csv", index)
      write.csv(grid, file.path(out, filename), row.names = FALSE, na = "", fileEncoding = "UTF-8")
      files[[length(files) + 1L]] <<- list(file = filename, level = level, coverage = "stored_tensor", row_count = nrow(grid),
        axes = list(source = as.list(axes[[1]]), target = as.list(axes[[2]]), interaction_name = as.list(axes[[3]])),
        context = context, object_name = object_name, parameters = options$parameter,
        upstream_filtering = "unknown; zeros may already reflect filterCommunication or other edits")
    }
  }
  for (name in names(objects)) {
    obj <- objects[[name]]
    if (!methods::is(obj, "CellChat")) stop("Expected CellChat object")
    nets <- if (identical(obj@options$mode, "merged")) obj@net else list(single = obj@net)
    for (part in names(nets)) {
      dataset <- if (identical(obj@options$mode, "merged")) paste(name, part, sep = "/") else name
      context <- list(dataset_id = dataset, condition = "unknown", patient_id = "unknown", species = "unknown",
        analysis_group = "unknown", cellchat_version = as.character(utils::packageVersion("CellChat")), database_version = database_version)
      if (!is.null(contexts)) {
        idx <- which(contexts$dataset_id == dataset)
        if (length(idx) != 1L) stop("contexts needs exactly one row for each dataset_id")
        for (nm in intersect(names(context), names(contexts))) context[[nm]] <- as.character(contexts[[nm]][idx])
      }
      lr <- if (identical(obj@options$mode, "merged")) obj@LR[[part]]$LRsig else obj@LR$LRsig
      emit(nets[[part]], lr, context, obj@DB, obj@options, name)
    }
  }
  jsonlite::write_json(list(format = "cellchat-export-v1", files = files, session = capture.output(sessionInfo()),
    scope = "all entries of stored net arrays, including zero/non-significant; not pre-inference universe"),
    file.path(out, "manifest.json"), auto_unbox = TRUE, pretty = TRUE, null = "null", na = "null")
  invisible(file.path(out, "manifest.json"))
}
