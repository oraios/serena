package com.example.testapp

import androidx.appcompat.app.AppCompatActivity
import android.os.Bundle

class AndroidActivity : AppCompatActivity() {
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // Use Java utilities from Kotlin
        val users = KotlinUtils.createSampleUsers()
        users.forEach { user ->
            JavaUtils.logMessage("Created user: ${user.name}")
        }
        
        // Filter adults using Java utility
        val adults = KotlinUtils.filterAdults(users)
        println("Found ${adults.size} adults")
        
        // Mixed language operations
        testCrossLanguageInteraction()
    }
    
    private fun testCrossLanguageInteraction() {
        val user = UserModel("Kotlin User", 28)
        
        // Java method call
        val formatted = JavaUtils.formatUserInfo(user)
        println("Formatted info: $formatted")
        
        // Kotlin processing
        KotlinUtils.processUser(user)
    }
    
    companion object {
        @JvmStatic
        fun callFromJava(message: String) {
            println("Kotlin method called from Java with message: $message")
        }
    }
}