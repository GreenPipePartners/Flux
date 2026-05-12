# Ignition (Jython) script
# Reads a list of tags and prints any Dataset values found.

# Fill this list with your tag paths
tagPaths = [
    # "[default]Folder/Tag1",
    # "[default]Folder/Tag2",
]

# Read all tag values at once
results = system.tag.readBlocking(tagPaths)

# Loop through results
for i in range(len(tagPaths)):
    tagPath = tagPaths[i]
    qualifiedValue = results[i]
    value = qualifiedValue.value

    print "=============================="
    print "Tag:", tagPath
    print "Quality:", qualifiedValue.quality
    print "Timestamp:", qualifiedValue.timestamp

    # Check if the value is a Dataset
    if hasattr(value, "getColumnCount"):
        print "Dataset Contents:"
        pyData = system.dataset.toPyDataSet(value)

        # Print column headers
        headers = []
        for col in range(value.getColumnCount()):
            headers.append(value.getColumnName(col))
        print "\t".join(headers)

        # Print rows
        for row in pyData:
            print "\t".join([str(cell) for cell in row])

    else:
        print "Value is not a Dataset:"
        print value
