import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
const path = "../outputs/IDC_modeling_table_cleaned_annotated_corrected.xlsx";
const wb = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
console.log((await wb.inspect({kind:"sheet", include:"id,name", maxChars:2000})).ndjson);
console.log((await wb.inspect({kind:"match", searchTerm:"Bevacizumab|Pinatuzumab Vedotin|Faricimab|Cetuximab|Necitumumab|Reslizumab|GSK3174998|Utomilumab|Trebananib|Isatuximab", options:{useRegex:true,maxResults:80}, maxChars:12000})).ndjson);
console.log((await wb.inspect({kind:"table", sheetId:"Cleaning_Audit", range:"A1:F12", include:"values,formulas", tableMaxRows:12, tableMaxCols:6, maxChars:8000})).ndjson);
console.log((await wb.inspect({kind:"match", searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options:{useRegex:true,maxResults:300}, summary:"final formula error scan", maxChars:3000})).ndjson);
