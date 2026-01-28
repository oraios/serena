/**
 * Controller class for Account operations
 */
public class AccountController {
    
    /**
     * Get all active accounts
     */
    public static List<Account> getActiveAccounts() {
        return [SELECT Id, Name, Industry FROM Account WHERE IsActive__c = true];
    }
    
    /**
     * Create a new account
     */
    public static Account createAccount(String name, String industry) {
        Account acc = new Account(
            Name = name,
            Industry = industry
        );
        insert acc;
        return acc;
    }
    
    /**
     * Update account industry
     */
    public static void updateAccountIndustry(Id accountId, String newIndustry) {
        Account acc = [SELECT Id FROM Account WHERE Id = :accountId];
        acc.Industry = newIndustry;
        update acc;
    }
}

