package com.example.testapp

import android.util.Log

object KotlinUtils {
    private const val TAG = "KotlinUtils"
    
    fun getGreeting(name: String): String {
        return "Hello from Kotlin, $name!"
    }
    
    fun processUser(user: UserModel) {
        val info = JavaUtils.formatUserInfo(user)
        Log.d(TAG, "Processing user: $info")
        
        if (JavaUtils.isAdult(user)) {
            println("User ${user.name} is an adult")
        } else {
            println("User ${user.name} is a minor")
        }
        
        // Call Java method from Kotlin
        MainActivity.callFromKotlin()
    }
    
    fun createSampleUsers(): List<UserModel> {
        return listOf(
            UserModel("Alice", 30),
            UserModel("Bob", 16),
            UserModel("Charlie", 25)
        )
    }
    
    fun filterAdults(users: List<UserModel>): List<UserModel> {
        return users.filter { JavaUtils.isAdult(it) }
    }
}