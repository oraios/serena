<?php

/**
 * Example WordPress-style plugin class for testing Intelephense symbol retrieval.
 *
 * This file is used to test that find_symbol works correctly for class methods
 * in PHP files, including both public and private static methods.
 *
 * @package TestRepo
 */

if ( ! defined( 'TEST_CONSTANT' ) ) {
    define( 'TEST_CONSTANT', true );
}

/**
 * A simple class with static methods, mirroring a WordPress webhook handler.
 */
class TestWebhookHandler {

    /**
     * Handle an incoming request.
     *
     * @param array $data Request data.
     * @return bool
     */
    public static function handle_request( array $data ): bool {
        $parsed = self::parse_data( $data );
        $profile_id = self::match_profile( $parsed['email'] );
        return $profile_id > 0;
    }

    /**
     * Parse raw data into a structured format.
     *
     * @param array $data Raw data.
     * @return array Parsed data.
     */
    private static function parse_data( array $data ): array {
        return array(
            'email'   => $data['email'] ?? '',
            'subject' => $data['subject'] ?? '',
            'body'    => $data['body'] ?? '',
        );
    }

    /**
     * Match a profile by email address.
     *
     * @param string $email Email address.
     * @return int Profile ID, or 0 if not found.
     */
    private static function match_profile( string $email ): int {
        if ( empty( $email ) ) {
            return 0;
        }
        return 42; // Simulated match.
    }
}

/**
 * A second class to test multi-class symbol retrieval.
 */
class TestProfileManager {

    /** @var int */
    private int $profile_id;

    public function __construct( int $profile_id ) {
        $this->profile_id = $profile_id;
    }

    /**
     * Get the profile ID.
     *
     * @return int
     */
    public function get_id(): int {
        return $this->profile_id;
    }

    /**
     * Update profile data.
     *
     * @param array $data Data to update.
     * @return bool
     */
    public function update( array $data ): bool {
        return ! empty( $data );
    }
}
