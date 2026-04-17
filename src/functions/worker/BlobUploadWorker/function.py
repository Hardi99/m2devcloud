{
    "scriptFile": "__init__.py",
    "bindings": [
        {
            "name": "inputblob",
            "type": "blobTrigger",
            "direction": "in",
            "path": "doc-storage/input/{name}",
            "connection": "docstorageprof_STORAGE"
        }
    ]
}