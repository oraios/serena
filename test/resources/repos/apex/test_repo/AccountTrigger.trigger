/**
 * Trigger for Account object
 */
trigger AccountTrigger on Account (before insert, before update, after insert, after update) {
    
    if (Trigger.isBefore) {
        if (Trigger.isInsert) {
            // Before insert logic
            for (Account acc : Trigger.new) {
                if (String.isBlank(acc.Industry)) {
                    acc.Industry = 'Other';
                }
            }
        }
        
        if (Trigger.isUpdate) {
            // Before update logic
            for (Account acc : Trigger.new) {
                Account oldAcc = Trigger.oldMap.get(acc.Id);
                if (acc.Name != oldAcc.Name) {
                    acc.Description = 'Name changed from ' + oldAcc.Name + ' to ' + acc.Name;
                }
            }
        }
    }
    
    if (Trigger.isAfter) {
        if (Trigger.isInsert || Trigger.isUpdate) {
            // After insert/update logic
            Set<Id> accountIds = new Set<Id>();
            for (Account acc : Trigger.new) {
                accountIds.add(acc.Id);
            }
            // Process accounts
        }
    }
}

