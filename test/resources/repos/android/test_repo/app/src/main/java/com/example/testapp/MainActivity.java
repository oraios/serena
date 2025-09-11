package com.example.testapp;

import androidx.appcompat.app.AppCompatActivity;
import android.os.Bundle;

public class MainActivity extends AppCompatActivity {

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        
        // Use Kotlin utilities from Java
        String greeting = KotlinUtils.getGreeting("Android");
        System.out.println(greeting);
        
        // Use Java utilities
        JavaUtils.logMessage("MainActivity started");
        
        // Cross-language interaction
        UserModel user = new UserModel("John Doe", 25);
        KotlinUtils.processUser(user);
    }
    
    public static void callFromKotlin() {
        System.out.println("Java method called from Kotlin!");
    }
}