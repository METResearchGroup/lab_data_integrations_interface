import { createClient } from "@/lib/supabase/server";
import type { EmailOtpType } from "@supabase/supabase-js";
import { type NextRequest, NextResponse } from "next/server";

/**
 * Consumes the one-time token from Supabase's invite and recovery emails.
 */
export async function GET(request: NextRequest) {
	const { searchParams } = request.nextUrl;
	const tokenHash = searchParams.get("token_hash");
	const type = searchParams.get("type") as EmailOtpType | null;

	if (!tokenHash || !type) {
		return NextResponse.redirect(
			new URL("/login?error=invalid_link", request.url),
		);
	}

	const supabase = await createClient();
	const { error } = await supabase.auth.verifyOtp({
		type,
		token_hash: tokenHash,
	});

	if (error) {
		return NextResponse.redirect(
			new URL("/login?error=expired_link", request.url),
		);
	}

	return NextResponse.redirect(new URL("/set-password", request.url));
}
