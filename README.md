# Progress so far
- looked at Lotta's file/script, realised that there still is a significant amount of ambiguity and it's not easily usable for my workflow - also, only ca. 50 percent of the entries were covered, the rest was ignored due to complexity
- explored the Abkürzungsverzeichnis to better understand the complexity
- created a plan for using the information in the glossary
    - expand all abbreviations where a simple rule suffices
    - let an LLM choose the most likely candidate for abbreviations where there are multiple candidates
    - then let an LLM normalise the text
- for this first the information in the glossary needs to be extracted, because it's definitely not yet in a form that can be used programatically
    - I decided to use a script for this, because this ensures reproducibility and makes all decisions I took explicit
    - in case I made a mistake somewhere (misunderstanding something about the glossary), it would also be easier to fix it, by fixing the script and re-running it
- got started on extracting the info (letting ChatGPT-5.4 create a first revision of a script for extracting the information for me)
    - since there is a lot of complexity behind the data and knowledge of Latin helps, using a model that is simply trained to programm, wouldn't have been as helpful, so I decided to use a commercial model for this task, which doesn't need to be reproducible (since the script itself ensures reproducibility)
- made some manual revisions on data in the glossary (there are a lot of inconsistencies and correcting some makes the extraction simpler)

# ToDos
- check that for all aliases the targets actually exist
- handle stuff (first understand what it means) like
    - `solutus/soluta`
    - alias of multiple things (siehe cap. und capel)
        - no alias entry or multiple entries
        - LLM_CANDIDATE
    - wieso hat Romanorum Imperator die Notiz "und ausgeschrieben: Romanum imperium; Romanum Imperium"?
    ```
    R. I.,Romanorum Imperator,Römischer Kaiser,,,,Romanorum imp.,Rom. imper.; Rom. Imperator,Rom. imp.; Rom. imperium; Roman. imperium,,R. I.,R. I.,R. I.,R. I.,R. I.; Romani imper.,und ausgeschrieben: Romanum imperium; Romanum Imperium,
    ,Romanum Imperium ?,,,,,,,,,,,,,,,
    ```
    - 