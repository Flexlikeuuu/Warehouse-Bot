/**
 * Google Apps Script Webhook для синхронизации Telegram-бота со спецификацией Google Таблицы.
 * 
 * ИНСТРУКЦИЯ ПО УСТАНОВКЕ:
 * 1. Откройте вашу Google Таблицу.
 * 2. В верхнем меню выберите: Расширения (Extensions) -> Apps Script.
 * 3. Удалите весь существующий код и вставьте содержимое этого файла.
 * 4. Нажмите синюю кнопку "Развернуть" (Deploy) в правом верхнем углу:
 *    -> "Управление развертываниями" (Manage deployments)
 *    -> Нажмите на иконку карандаша (Редактировать)
 *    -> В поле "Версия" выберите "Новая версия" (New version)
 *    -> Нажмите "Развернуть" (Deploy).
 */

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName("Лист1") || ss.getActiveSheet();
    
    var dateStr = data.date; // Например "04.11.2026"
    var parts = dateStr.split(".");
    var targetDay = parseInt(parts[0], 10);
    var targetMonth = parseInt(parts[1], 10);
    var targetYear = parseInt(parts[2], 10);
    
    var lastCol = Math.max(sheet.getLastColumn(), 9);
    var targetCol = -1;
    
    // 1. Поиск существующего столбца с текущей датой в строке 3 (начиная со столбца 10)
    for (var c = 10; c <= lastCol; c++) {
      var cell = sheet.getRange(3, c);
      var cellVal = cell.getValue();
      var dispVal = cell.getDisplayValue();
      
      // Проверка, если значение ячейки является объектом Date
      if (cellVal instanceof Date) {
        if (cellVal.getDate() === targetDay && 
            (cellVal.getMonth() + 1) === targetMonth && 
            cellVal.getFullYear() === targetYear) {
          targetCol = c;
          break;
        }
      }
      
      // Проверка по строковому представлению
      var s = String(dispVal || cellVal).trim();
      if (s === dateStr || 
          s === (targetMonth + "/" + targetDay + "/" + targetYear) ||
          s === (targetDay + "." + targetMonth + "." + targetYear) ||
          s.indexOf(targetDay + "." + targetMonth) !== -1) {
        targetCol = c;
        break;
      }
    }
    
    // 2. Если столбец с текущей датой не найден — создаем новый
    if (targetCol === -1) {
      targetCol = lastCol + 1;
      var newDate = new Date(targetYear, targetMonth - 1, targetDay);
      sheet.getRange(3, targetCol).setValue(newDate).setNumberFormat("dd.MM.yyyy");
      sheet.getRange(4, targetCol).setValue("объем");
    }
    
    // 3. Запись объемов в найденный столбец
    var isOverwrite = Boolean(data.overwrite);
    if (data.items && data.items.length > 0) {
      for (var i = 0; i < data.items.length; i++) {
        var it = data.items[i];
        if (it.row_idx) {
          var itemCell = sheet.getRange(it.row_idx, targetCol);
          var curVal = itemCell.getValue();
          
          if (!isOverwrite && typeof curVal === "number" && curVal > 0) {
            // Если уже был внесен объем за сегодня — суммируем
            itemCell.setValue(curVal + Number(it.volume));
          } else {
            // Иначе записываем новое значение
            itemCell.setValue(Number(it.volume));
          }
        }
      }
    }
    
    return ContentService.createTextOutput(JSON.stringify({
      status: "ok", 
      col: targetCol,
      is_new_column: (targetCol > lastCol)
    })).setMimeType(ContentService.MimeType.JSON);
    
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: "error", 
      message: err.toString()
    })).setMimeType(ContentService.MimeType.JSON);
  }
}

function doGet(e) {
  return ContentService.createTextOutput(JSON.stringify({
    status: "ok", 
    message: "Google Apps Script Webhook активен и готов к работе"
  })).setMimeType(ContentService.MimeType.JSON);
}
