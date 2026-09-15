# Put your chapters here

One folder per chapter, each one an unzipped Overleaf export
(Menu -> Download -> Source).

Name the folders so that they sort in the order the chapters should appear:

    chapters/
      01-free-economic-zones/
      02-care-blocks/
      03-ai-innovation/

Then, from the root of the thesis:

    python3 tools/import_chapter.py

Nothing else in the folder needs renaming: the script reads each paper's own
main .tex file and works out the rest.
